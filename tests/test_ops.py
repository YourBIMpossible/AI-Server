"""WP-E ops tooling: preload, endpoint-down watch, and the committed gateway config."""
import importlib.util
import re
from pathlib import Path

from aiserver import LLM, load_config

REPO = Path(__file__).resolve().parent.parent
DOWN = "http://127.0.0.1:1"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _llm(url):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"INFERENCE_BASE_URL": url})
    return LLM(cfg, retries=0, timeout=5)


# --- endpoint watch -----------------------------------------------------
def test_watch_state_machine_alerts_once_after_the_window_then_recovers():
    w = _load("endpoint_watch")
    s, ev = w.step({}, False, "down", now=1000, minutes=3)
    assert ev is None and s["down_since"] == 1000
    s, ev = w.step(s, False, "down", now=1000 + 179, minutes=3)
    assert ev is None
    s, ev = w.step(s, False, "down", now=1000 + 180, minutes=3)
    assert ev == "ALERT" and s["alerted"]
    s, ev = w.step(s, False, "down", now=1000 + 600, minutes=3)
    assert ev is None  # one alert per outage
    s, ev = w.step(s, True, "serving", now=2000, minutes=3)
    assert ev == "RECOVERED" and s == {"down_since": None, "alerted": False, "detail": "serving"}
    s, ev = w.step(s, True, "serving", now=2060, minutes=3)
    assert ev is None


def test_watch_a_blip_shorter_than_the_window_never_alerts():
    w = _load("endpoint_watch")
    s, _ = w.step({}, False, "down", now=0, minutes=3)
    s, ev = w.step(s, True, "serving", now=60, minutes=3)
    assert ev is None


def test_watch_check_against_mock_and_down_endpoint(mock_endpoint):
    w = _load("endpoint_watch")
    assert w.check(_llm(mock_endpoint), generate=True) == (True, "serving")
    ok, detail = w.check(_llm(DOWN), generate=False)
    assert ok is False and detail


def test_watch_main_end_to_end(tmp_path, monkeypatch, capsys):
    w = _load("endpoint_watch")
    state = tmp_path / "s.json"
    monkeypatch.setenv("INFERENCE_BASE_URL", DOWN)
    assert w.main(["--minutes", "1", "--state", str(state)], now=0) == 1
    assert w.main(["--minutes", "1", "--state", str(state)], now=61) == 1
    assert "<2>ALERT" in capsys.readouterr().err
    w.main(["--minutes", "1", "--state", str(state)], now=120)
    assert "ALERT" not in capsys.readouterr().err  # not repeated


def test_watch_corrupt_state_file_is_treated_as_fresh(tmp_path):
    w = _load("endpoint_watch")
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    assert w.load_state(p) == {}


# --- preload ------------------------------------------------------------
def test_preload_wait_and_warm_against_mock(mock_endpoint):
    p = _load("preload")
    llm = _llm(mock_endpoint)
    assert p.wait_for(llm, 1) is True
    assert p.available_models(llm) == ["mock-model"]
    assert p.warm(llm, "mock-model") >= 0


def test_preload_wait_gives_up_on_a_down_endpoint():
    p = _load("preload")
    ticks = iter(range(0, 1000, 5))
    assert p.wait_for(_llm(DOWN), 10, sleep=lambda s: None, clock=lambda: next(ticks)) is False


def test_preload_missing_models_normalizes_latest_tags():
    p = _load("preload")
    assert p.missing_models(["nomic-embed-text", "qwen2.5-coder:14b", "x:1"],
                            ["nomic-embed-text:latest", "qwen2.5-coder:14b"]) == ["x:1"]


def test_preload_pull_without_a_runner_cli_reports_missing(capsys):
    p = _load("preload")
    assert p.pull(["a:1"], cli=None) == ["a:1"]
    assert "a:1" in capsys.readouterr().out


def test_preload_main_fails_when_endpoint_down(monkeypatch):
    p = _load("preload")
    monkeypatch.setenv("INFERENCE_BASE_URL", DOWN)
    assert p.main(["--wait", "0"]) == 1


# --- committed gateway config -------------------------------------------
def test_gateway_config_is_private_by_default_and_portable_only():
    text = (REPO / "ops" / "Caddyfile").read_text(encoding="utf-8")
    caddy = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))  # directives only
    assert "{$GATEWAY_BIND:127.0.0.1}" in caddy  # loopback unless the box's env says otherwise
    assert "0.0.0.0" not in caddy and "ollama" not in caddy.lower()
    assert re.search(r'header Authorization "Bearer \{\$INFERENCE_API_KEY\}"', caddy)
    assert "path /v1/*" in caddy  # runner-native paths are not proxied


def test_gateway_unit_refuses_a_missing_or_short_key():
    unit = (REPO / "ops" / "systemd" / "aiserver-gateway.service").read_text(encoding="utf-8")
    assert '"$${#INFERENCE_API_KEY}" -ge 32' in unit


def test_setup_ops_refuses_public_binds():
    script = (REPO / "scripts" / "setup-ops.sh").read_text(encoding="utf-8")
    assert "refusing to bind non-private address" in script


def test_setup_ops_never_sources_the_environment_file_and_keeps_the_key():
    script = (REPO / "scripts" / "setup-ops.sh").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in script.splitlines() if not ln.strip().startswith("#"))
    assert ". /etc/ai-server/gateway.env" not in code and "source /etc/ai-server/gateway.env" not in code
    assert 'if [ -f /etc/ai-server/gateway.env ]; then' in code  # an existing key is never regenerated
    assert "systemctl restart aiserver-gateway.service" in code  # a re-run applies config changes


def test_crash_test_report_never_pastes_shell_values_into_python_source():
    script = (REPO / "scripts" / "crash-recovery-test.sh").read_text(encoding="utf-8")
    report = script[script.index("python3 - \"$report\""):]
    assert "<<'EOF'" in report  # quoted heredoc: no shell expansion inside the Python
    assert '"""$' not in report and "os.environ" in report
