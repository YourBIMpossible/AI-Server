from aiserver.config import load_config


def test_defaults_and_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL", "test-model")
    monkeypatch.setenv("OUT", str(tmp_path / "o"))
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    cfg = load_config(dotenv=tmp_path / "nonexistent.env")
    assert cfg.model == "test-model"
    assert cfg.base_url == "http://localhost:11434"  # default, no override
    assert cfg.out.is_absolute()


def test_explicit_overrides_win(tmp_path):
    cfg = load_config(
        dotenv=tmp_path / "none.env",
        overrides={"OLLAMA_HOST": "http://box:11434/", "DIGEST_DAYS": "3"},
    )
    assert cfg.base_url == "http://box:11434"  # trailing slash stripped
    assert cfg.digest_days == 3


def test_dotenv_is_read(tmp_path):
    (tmp_path / "x.env").write_text("MODEL=from-dotenv\n# comment\n", encoding="utf-8")
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
    (tmp_path / "x.env").write_text('MODEL="qwen2.5-coder:14b"\n', encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"


def test_dotenv_strips_matching_single_quotes(tmp_path):
    (tmp_path / "x.env").write_text("MODEL='qwen2.5-coder:14b'\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"


def test_dotenv_leaves_mismatched_quote_untouched(tmp_path):
    (tmp_path / "x.env").write_text("MODEL=\"unterminated\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == '"unterminated'


# --- CONFIG-2: a blank value must not beat the built-in default; casts must name the key --


def test_blank_dotenv_value_does_not_override_default(tmp_path):
    (tmp_path / "x.env").write_text("MODEL=\n", encoding="utf-8")
    cfg = load_config(dotenv=tmp_path / "x.env", overrides={"OUT": str(tmp_path)})
    assert cfg.model == "qwen2.5-coder:14b"  # built-in default, not ''


def test_blank_env_var_does_not_override_default(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL", "")
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
