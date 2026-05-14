from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .config import LLM_CONFIG_SECRETS_PATH


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_llm_secret_map() -> Dict[str, str]:
    if not LLM_CONFIG_SECRETS_PATH.exists():
        return {}
    try:
        payload = json.loads(LLM_CONFIG_SECRETS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in payload.items()
        if isinstance(value, str) and value
    }


def save_llm_secret_map(data: Dict[str, str]) -> None:
    ensure_parent_dir(LLM_CONFIG_SECRETS_PATH)
    LLM_CONFIG_SECRETS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_llm_api_key(config_id: int, fallback: Optional[str] = None) -> Optional[str]:
    value = load_llm_secret_map().get(str(config_id))
    if value:
        return value
    if fallback:
        set_llm_api_key(config_id, fallback)
        return fallback
    return None


def set_llm_api_key(config_id: int, api_key: str) -> None:
    data = load_llm_secret_map()
    data[str(config_id)] = api_key
    save_llm_secret_map(data)


def mask_api_key(api_key: Optional[str]) -> str:
    if not api_key:
        return "未配置"
    if len(api_key) < 10:
        return "已配置"
    return f"{api_key[:6]}...{api_key[-4:]}"
