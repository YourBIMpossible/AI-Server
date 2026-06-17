"""aiserver — shared library for the local-LLM inference + automation platform.

Public API:
    from aiserver import load_config, LLM, LLMError, get_logger
"""
from .client import LLM, LLMError
from .config import Config, load_config
from .log import get_logger

__all__ = ["Config", "load_config", "LLM", "LLMError", "get_logger"]
__version__ = "0.1.0"
