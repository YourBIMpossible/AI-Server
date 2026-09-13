import pytest

from aiserver.config import load_config


def test_defaults_and_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("INFERENCE_MODEL", "test-model")
    monkeypatch.setenv("OUT", str(tmp_path / "o"))
    monkeypatch.delenv("INFERENCE_BASE_URL", raising=False)
    cfg = load_config(dotenv=tmp_path / "nonexistent.env")
    assert cfg.model == "test-model"
    assert cfg.base_url == "http://localhost:11434/v1"  # default, no override
    assert cfg.out.is_absolute()


def test_explicit_overrides_win(tmp_path):
    cfg = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"INFERENCE_BASE_URL": "http://box:11434/", "DIGEST_DAYS": "3"},
    )
    assert cfg.base_url == "http://box:11434/v1"  # trailing slash stripped, /v1 added
    assert cfg.digest_days == 3


# --- Runner-neutral endpoint contract (2026-09-11) -----------------------------
# The setting names an OpenAI-compatible base URL, not an Ollama host. These pin the
# two behaviours a runner swap depends on: `/v1` is implied but never doubled, and an
# explicit path (a gateway mounting the API elsewhere) is left alone.


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("http://box:11434", "http://box:11434/v1"),
        ("http://box:11434/", "http://box:11434/v1"),
        ("http://box:11434/v1", "http://box:11434/v1"),
        ("http://box:11434/v1/", "http://box:11434/v1"),
        ("http://gw.example/llm/openai/v1", "http://gw.example/llm/openai/v1"),
    ],
)
def test_base_url_normalization(tmp_path, raw, expected):
    cfg = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"OUT": str(tmp_path), "INFERENCE_BASE_URL": raw},
    )
    assert cfg.base_url == expected


def test_stale_ollama_host_in_dotenv_fails_loudly(tmp_path):
    """A .env left over from before the rename must not silently fall back to
    localhost -- on the box that would point every client at the wrong machine."""
    (tmp_path / "x.env").write_text("OLLAMA_HOST=http://box:11434\n", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert "INFERENCE_BASE_URL" in str(e.value)


def test_ollama_host_alongside_new_key_is_ignored(tmp_path):
    """Ollama's own server-side bind address uses the same name, so a .env that
    carries both is legitimate: the new key wins, no error."""
    (tmp_path / "x.env").write_text(
        "OLLAMA_HOST=0.0.0.0:11434\nINFERENCE_BASE_URL=http://box:11434/v1\n",
        encoding="utf-8",
    )
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.base_url == "http://box:11434/v1"


def test_stale_model_keys_fail_loudly(tmp_path):
    """MODEL/EMBED_MODEL were renamed with the endpoint contract. Silently using the
    built-in default would send every job at the wrong model."""
    for old, new in (("MODEL", "INFERENCE_MODEL"), ("EMBED_MODEL", "INFERENCE_EMBED_MODEL")):
        (tmp_path / "x.env").write_text(f"{old}=something\n", encoding="utf-8")
        with pytest.raises(ValueError) as e:
            load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
        assert new in str(e.value)


def test_inference_api_key_defaults_empty_and_overrides(tmp_path):
    default = load_config(dotenv=tmp_path / "none.env", overrides={"OUT": str(tmp_path)})
    assert default.inference_api_key == ""
    with_key = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"OUT": str(tmp_path), "INFERENCE_API_KEY": "sk-local"},
    )
    assert with_key.inference_api_key == "sk-local"


def test_dotenv_is_read(tmp_path):
    (tmp_path / "x.env").write_text("INFERENCE_MODEL=from-dotenv\n# comment\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "from-dotenv"


def test_eval_pass_threshold_default_and_override(tmp_path):
    default = load_config(dotenv=tmp_path / "none.env", overrides={"OUT": str(tmp_path)})
    assert default.eval_pass_threshold == 0.8
    overridden = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"OUT": str(tmp_path), "EVAL_PASS_THRESHOLD": "0.6"},
    )
    assert overridden.eval_pass_threshold == 0.6


def test_baseline_model_default_and_override(tmp_path):
    default = load_config(dotenv=tmp_path / "none.env", overrides={"OUT": str(tmp_path)})
    assert default.baseline_model == "claude-opus-4-8"
    overridden = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"OUT": str(tmp_path), "BASELINE_MODEL": "claude-sonnet-5"},
    )
    assert overridden.baseline_model == "claude-sonnet-5"


# --- CONFIG-1: quoted .env values must not leak the quote characters -----------


def test_dotenv_strips_matching_double_quotes(tmp_path):
    (tmp_path / "x.env").write_text('INFERENCE_MODEL="qwen2.5-coder:14b"\n', encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"


def test_dotenv_strips_matching_single_quotes(tmp_path):
    (tmp_path / "x.env").write_text("INFERENCE_MODEL='qwen2.5-coder:14b'\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"


def test_dotenv_leaves_mismatched_quote_untouched(tmp_path):
    (tmp_path / "x.env").write_text("INFERENCE_MODEL=\"unterminated\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == '"unterminated'


# --- CONFIG-2: a blank value must not beat the built-in default; casts must name the key --


def test_blank_dotenv_value_does_not_override_default(tmp_path):
    (tmp_path / "x.env").write_text("INFERENCE_MODEL=\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"  # built-in default, not ''


def test_blank_env_var_does_not_override_default(monkeypatch, tmp_path):
    monkeypatch.setenv("INFERENCE_MODEL", "")
    cfg = load_config(dotenv=tmp_path / "none.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"


def test_invalid_digest_days_raises_key_named_error(tmp_path):
    (tmp_path / "x.env").write_text("DIGEST_DAYS=not-a-number\n", encoding="utf-8")
    try:
        load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "DIGEST_DAYS" in str(e)
        assert "not-a-number" in str(e)
