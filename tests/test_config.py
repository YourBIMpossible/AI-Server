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
