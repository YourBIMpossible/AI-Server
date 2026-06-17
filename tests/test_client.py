import pytest

from aiserver.client import LLM, LLMError
from aiserver.config import load_config


def _cfg(tmp_path, host):
    return load_config(dotenv=tmp_path / "none.env", overrides={"OLLAMA_HOST": host})


def test_chat_and_embed(mock_endpoint, tmp_path):
    llm = LLM(_cfg(tmp_path, mock_endpoint))
    assert llm.ping() is True
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    vecs = llm.embed(["a", "b"])
    assert vecs and isinstance(vecs[0], list) and len(vecs[0]) == 3


def test_endpoint_down_raises(tmp_path):
    llm = LLM(_cfg(tmp_path, "http://127.0.0.1:1"), retries=0, timeout=1)
    assert llm.ping() is False
    with pytest.raises(LLMError):
        llm.chat([{"role": "user", "content": "hi"}])
