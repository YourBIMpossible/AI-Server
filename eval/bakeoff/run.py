"""WP-H bakeoff harness: drive ONE endpoint through the frozen protocol, emit raw per-request records.

    python -m eval.bakeoff.run measure --runner NAME --base-url URL --model M --phase warm|cold|probes
                                       [--reps N] [--ready-since EPOCH] [--out DIR]
    python -m eval.bakeoff.run report RUNNER_A_DIR_OR_FILES... --out DIR

Talks only through aiserver.client.LLM -- the OpenAI-compatible surface. Starting, stopping and
unloading runners is ops tooling (scripts/bakeoff-runner.sh), never this file. See protocol.md.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # repo root for `aiserver`

from aiserver import LLM, LLMError, load_config  # noqa: E402

from eval.run import case_prompt, load_cases  # noqa: E402

LONG_CASES = {"ops_log": "long-digest-ops", "worker_log": "long-extract-worker-errors", "docs_corpus": "long-rag-retention"}
DECODE_PROMPT = "Write the integers from 1 to 400 in order, separated by single spaces. Output nothing else."
TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    },
}]
INCIDENT_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "count": {"type": "integer"},
        "services": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["severity", "count", "services"],
    "additionalProperties": False,
}


# --- pure helpers --------------------------------------------------------
def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile; None for no data."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = max(1, math.ceil(p / 100 * len(vals)))
    return vals[k - 1]


def derive(timed: dict) -> dict:
    usage = timed.get("usage") or {}
    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
    ttft, total = timed.get("ttft_s"), timed.get("total_s")
    prefill = pt / ttft if pt and ttft else None
    decode = (ct - 1) / (total - ttft) if ct and ct > 1 and ttft is not None and total and total > ttft else None
    return {"prompt_tokens": pt, "completion_tokens": ct, "prefill_tok_s": prefill, "decode_tok_s": decode}


def timing_prompt(doc: str, rep: int) -> str:
    case = next(c for c in load_cases() if c["id"] == LONG_CASES[doc])
    return f"[bakeoff {doc} rep {rep}]\n" + case_prompt(case)


def check_schema_output(text: str) -> dict:
    try:
        obj = json.loads(text)
    except ValueError:
        return {"parsed": False, "conforms": False, "why": "not JSON"}
    if not isinstance(obj, dict):
        return {"parsed": True, "conforms": False, "why": "not an object"}
    problems = []
    if set(obj) != {"severity", "count", "services"}:
        problems.append(f"keys {sorted(obj)}")
    if obj.get("severity") not in ("low", "medium", "high"):
        problems.append(f"severity {obj.get('severity')!r}")
    if not isinstance(obj.get("count"), int) or isinstance(obj.get("count"), bool):
        problems.append("count not integer")
    if not (isinstance(obj.get("services"), list) and all(isinstance(s, str) for s in obj["services"])):
        problems.append("services not list[str]")
    return {"parsed": True, "conforms": not problems, "why": "; ".join(problems) or None}


# --- GPU memory sampler (hardware, not runner-native; degrades to None) ----
class VramSampler:
    def __init__(self, interval_ms: int = 250):
        self.interval_ms, self.peak, self._proc, self._t = interval_ms, None, None, None

    def __enter__(self):
        try:
            self._proc = subprocess.Popen(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", f"-lms={self.interval_ms}"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            )
        except OSError:
            return self
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()
        return self

    def _read(self):
        for line in self._proc.stdout:
            try:
                v = int(line.strip().split(",")[0])
            except ValueError:
                continue
            self.peak = v if self.peak is None else max(self.peak, v)

    def __exit__(self, *exc):
        if self._proc:
            time.sleep(self.interval_ms / 1000 * 2)
            self._proc.terminate()
            self._proc.wait(timeout=5)


# --- measurement ---------------------------------------------------------
def timed_record(llm: LLM, model: str, prompt: str, *, max_tokens: int, **meta) -> dict:
    rec = {"ts": datetime.now(timezone.utc).isoformat(), **meta}
    with VramSampler() as vram:
        try:
            t = llm.chat_timed([{"role": "user", "content": prompt}], model=model, temperature=0, max_tokens=max_tokens)
        except LLMError as e:
            rec.update({"error": str(e)[:1000]})
            t = None
    rec["vram_peak_mib"] = vram.peak
    if t is not None:
        rec.update({k: t[k] for k in ("ttft_s", "ttfc_s", "total_s", "finish_reason", "chunks", "usage", "server_timings")})
        rec.update(derive(t))
        rec["content_head"] = t["content"][:300]
        rec["error"] = None
    return rec


def wait_ready(llm: LLM, since_epoch: float, timeout: float = 600) -> float | None:
    while time.time() - since_epoch < timeout:
        try:
            if llm.ping():
                return time.time() - since_epoch
        except OSError:
            pass
        time.sleep(0.25)
    return None


def phase_warm(llm, model, runner, reps):
    llm.chat_timed([{"role": "user", "content": "Reply with OK."}], model=model, temperature=0, max_tokens=4)  # untimed warm-up
    for doc in LONG_CASES:
        for rep in range(1, reps + 1):
            yield timed_record(llm, model, timing_prompt(doc, rep), max_tokens=128,
                               runner=runner, phase="warm", doc=doc, rep=rep)
    for rep in range(1, 4):
        yield timed_record(llm, model, DECODE_PROMPT, max_tokens=512, runner=runner, phase="decode", doc="decode", rep=rep)


def phase_cold(llm, model, runner, ready_since, cycle):
    ready = 0.0 if ready_since is None else wait_ready(llm, ready_since)
    rec = timed_record(llm, model, timing_prompt("ops_log", 100 + cycle), max_tokens=128,
                       runner=runner, phase="cold", doc="ops_log", rep=cycle)
    rec["ready_s"] = ready
    rec["cold_total_s"] = None if ready is None or rec.get("ttft_s") is None else ready + rec["ttft_s"]
    yield rec


def phase_probes(llm, model, runner):
    base = {"runner": runner, "phase": "probe"}

    try:
        msg = llm.chat_message([{"role": "user", "content": "What is the weather in Paris right now? Use the tool."}],
                               model=model, temperature=0, tools=TOOLS)
        calls = [{"name": c.name, "arguments": c.arguments, "parse_error": c.parse_error} for c in msg.tool_calls]
        real = any(c["name"] == "get_weather" and str(c["arguments"].get("city", "")).lower().startswith("paris")
                   and not c["parse_error"] for c in calls)
        yield {**base, "probe": "tool_call", "pass": real, "tool_calls": calls,
               "prose_tool_call": (not calls) and "get_weather" in (msg.content or ""), "content_head": (msg.content or "")[:300]}
    except LLMError as e:
        yield {**base, "probe": "tool_call", "pass": False, "error": str(e)[:500]}

    try:
        text = llm.chat(
            [{"role": "user", "content": "Describe this incident as JSON with fields severity (low/medium/high), count "
              "(integer) and services (list of names), and ALSO add a field called notes with your commentary. "
              "Incident: api, billing and auth returned HTTP 500 for 20 minutes; customers were affected."}],
            model=model, temperature=0,
            response_format={"type": "json_schema", "json_schema": {"name": "incident", "strict": True, "schema": INCIDENT_SCHEMA}},
        )
        chk = check_schema_output(text)
        yield {**base, "probe": "json_schema", "pass": chk["conforms"], **chk, "content_head": text[:300]}
    except LLMError as e:
        yield {**base, "probe": "json_schema", "pass": False, "error": str(e)[:500]}

    try:
        t = llm.chat_timed([{"role": "user", "content": "Count from 1 to 10."}], model=model, temperature=0, max_tokens=64)
        ok = t["chunks"] > 1 and t["finish_reason"] in ("stop", "length") and bool(t["content"]) and bool(t["usage"])
        yield {**base, "probe": "streaming", "pass": ok, "chunks": t["chunks"], "finish_reason": t["finish_reason"],
               "usage": t["usage"]}
    except LLMError as e:
        yield {**base, "probe": "streaming", "pass": False, "error": str(e)[:500]}

    try:
        llm.chat([{"role": "user", "content": "hi"}], model="no-such-model:0")
        yield {**base, "probe": "unknown_model", "pass": False, "error": None, "note": "accepted an unknown model name"}
    except LLMError as e:
        yield {**base, "probe": "unknown_model", "pass": True, "error": str(e)[:500]}

    oversize = timing_prompt("ops_log", 900) + "\n\n" + timing_prompt("ops_log", 901)
    rec = timed_record(llm, model, oversize, max_tokens=8, runner=runner, phase="probe", doc="oversize", rep=1)
    pt = rec.get("prompt_tokens")
    rec.update({"probe": "oversize_prompt",
                "outcome": "rejected" if rec.get("error") else ("truncated_silently" if pt and pt < 40000 else "accepted"),
                "pass": bool(rec.get("error"))})  # a silent truncation is the failure mode that hurts
    yield rec

    ids = []
    try:
        import urllib.request

        req = urllib.request.Request(f"{llm.cfg.base_url}/models", headers=llm._headers())
        with urllib.request.urlopen(req, timeout=10) as r:
            ids = [m.get("id") for m in json.load(r).get("data", [])]
    except OSError as e:
        yield {**base, "probe": "models_listing", "pass": False, "error": str(e)}
    else:
        yield {**base, "probe": "models_listing", "pass": model in ids, "ids": ids}


def measure(args) -> Path:
    cfg = load_config(overrides={"INFERENCE_BASE_URL": args.base_url, "INFERENCE_MODEL": args.model})
    llm = LLM(cfg, timeout=1800, retries=0)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out / f"{args.runner}-{args.phase}-{stamp}.jsonl"
    if args.phase == "warm":
        records = phase_warm(llm, args.model, args.runner, args.reps)
    elif args.phase == "cold":
        records = phase_cold(llm, args.model, args.runner, args.ready_since, args.cycle)
    else:
        records = phase_probes(llm, args.model, args.runner)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            rec.setdefault("model", args.model)
            f.write(json.dumps(rec) + "\n")
            f.flush()
            brief = {k: rec.get(k) for k in ("phase", "doc", "rep", "probe", "pass", "ttft_s", "prefill_tok_s", "decode_tok_s",
                                             "ready_s", "vram_peak_mib", "error") if rec.get(k) is not None}
            print(json.dumps(brief), flush=True)
    return path


# --- report --------------------------------------------------------------
def _fmt(v, nd=2):
    return "—" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


def load_records(paths: list[Path]) -> list[dict]:
    recs = []
    for p in paths:
        files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
        for f in files:
            recs += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
    return recs


def report(records: list[dict], *, today: str, header: str = "") -> str:
    runners = sorted({r["runner"] for r in records})
    by = lambda runner, **kv: [r for r in records if r["runner"] == runner and all(r.get(k) == v for k, v in kv.items())]  # noqa: E731
    lines = [f"# Runner bakeoff — {today}", "", header, "", "## Warm, per long document (5 reps, unique prefixes)", "",
             "| Document | Runner | prompt tokens | TTFT p50 s | TTFT p90 s | TTFT max s | prefill tok/s p50 | peak VRAM MiB | errors |",
             "|---|---|---|---|---|---|---|---|---|"]
    for doc in LONG_CASES:
        for rn in runners:
            rs = by(rn, phase="warm", doc=doc)
            ok = [r for r in rs if not r.get("error")]
            lines.append(f"| {doc} | {rn} | {_fmt(percentile([r.get('prompt_tokens') for r in ok], 50), 0)} | "
                         f"{_fmt(percentile([r['ttft_s'] for r in ok], 50))} | {_fmt(percentile([r['ttft_s'] for r in ok], 90))} | "
                         f"{_fmt(percentile([r['ttft_s'] for r in ok], 100))} | {_fmt(percentile([r['prefill_tok_s'] for r in ok], 50), 0)} | "
                         f"{_fmt(max([r['vram_peak_mib'] for r in ok if r.get('vram_peak_mib')] or [None]) if ok else None, 0)} | "
                         f"{len(rs) - len(ok)}/{len(rs)} |")
    lines += ["", "## Decode (512-token enumeration, 3 reps)", "", "| Runner | decode tok/s p50 | min | max |", "|---|---|---|---|"]
    for rn in runners:
        d = [r.get("decode_tok_s") for r in by(rn, phase="decode") if not r.get("error")]
        lines.append(f"| {rn} | {_fmt(percentile(d, 50), 1)} | {_fmt(percentile(d, 0.0001), 1)} | {_fmt(percentile(d, 100), 1)} |")
    lines += ["", "## Cold (process-cold; ready + first-request TTFT on ops_log)", "",
              "| Runner | cycles | ready s (p50) | TTFT s (p50) | cold total s p50 | max |", "|---|---|---|---|---|---|"]
    for rn in runners:
        c = [r for r in by(rn, phase="cold") if not r.get("error")]
        lines.append(f"| {rn} | {len(c)} | {_fmt(percentile([r.get('ready_s') for r in c], 50))} | "
                     f"{_fmt(percentile([r.get('ttft_s') for r in c], 50))} | {_fmt(percentile([r.get('cold_total_s') for r in c], 50))} | "
                     f"{_fmt(percentile([r.get('cold_total_s') for r in c], 100))} |")
    probes = sorted({r["probe"] for r in records if r.get("phase") == "probe"})
    lines += ["", "## Correctness probes", "", "| Probe | " + " | ".join(runners) + " |", "|---|" + "---|" * len(runners)]
    for pr in probes:
        cells = []
        for rn in runners:
            rs = [r for r in records if r["runner"] == rn and r.get("probe") == pr]
            if not rs:
                cells.append("—")
                continue
            r = rs[-1]
            extra = r.get("outcome") or r.get("why") or ("prose tool call" if r.get("prose_tool_call") else "")
            cells.append(("pass" if r.get("pass") else "FAIL") + (f" ({extra})" if extra else ""))
        lines.append(f"| {pr} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--runner", required=True)
    m.add_argument("--base-url", required=True)
    m.add_argument("--model", required=True)
    m.add_argument("--phase", choices=["warm", "cold", "probes"], required=True)
    m.add_argument("--reps", type=int, default=5)
    m.add_argument("--cycle", type=int, default=1)
    m.add_argument("--ready-since", type=float, help="epoch when the runner process was started (cold, process start)")
    m.add_argument("--out", default=str(REPO / "out" / "bakeoff"))
    r = sub.add_parser("report")
    r.add_argument("paths", nargs="+", type=Path)
    r.add_argument("--out", type=Path, default=REPO / "out" / "bakeoff")
    r.add_argument("--header", default="")
    args = ap.parse_args(argv)
    if args.cmd == "measure":
        print(f"[OK] wrote {measure(args)}")
        return 0
    today = datetime.now().strftime("%Y-%m-%d")
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / f"report-{today}.md"
    dest.write_text(report(load_records(args.paths), today=today, header=args.header), encoding="utf-8")
    print(f"[OK] wrote {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
