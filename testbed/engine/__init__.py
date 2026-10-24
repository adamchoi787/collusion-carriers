"""Core engine: game loop, media and cover defaults, visibility and decoys, messages,
belief probes, checkpoints and branching, plugins, JSONL logging, config loader."""
from .config import (config_from_dict, config_from_yaml, config_to_dict, config_to_yaml,
                     effective_visibility, load_config, save_config)
from .factory import make_agent, parse_agent_arg, register_agent_kind
from .game import Engine, RunResult, branch, run
from .plugins import Plugin, SwapPlugin
from .storage import LocalStorage, MemoryStorage, Storage, read_log

__all__ = [
    "Engine", "RunResult", "run", "branch", "Plugin", "SwapPlugin",
    "Storage", "LocalStorage", "MemoryStorage", "read_log",
    "config_to_dict", "config_from_dict", "config_to_yaml", "config_from_yaml", "load_config",
    "save_config", "effective_visibility", "make_agent", "parse_agent_arg", "register_agent_kind",
]
