"""Configuration loader for scalping bot. Loads .env for Telegram credentials."""
import os
from pathlib import Path
from typing import Any

import yaml

# Load .env so TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are available
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass  # optional: pip install python-dotenv


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load YAML config; override with env / .env (TELEGRAM_*)."""
    if config_path is None:
        base = Path(__file__).resolve().parent
        config_path = str(base / "settings.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f) or {}
    # Env overrides (from .env or environment)
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        cfg.setdefault("telegram", {})["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID"):
        cfg.setdefault("telegram", {})["chat_id"] = os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("RITHMIC_USER"):
        cfg.setdefault("data", {}).setdefault("rithmic", {})["user"] = os.getenv("RITHMIC_USER")
    if os.getenv("RITHMIC_PASSWORD"):
        cfg.setdefault("data", {}).setdefault("rithmic", {})["password"] = os.getenv("RITHMIC_PASSWORD")
    if os.getenv("CQG_USER"):
        cfg.setdefault("data", {}).setdefault("cqg", {})["user"] = os.getenv("CQG_USER")
    if os.getenv("CQG_PASSWORD"):
        cfg.setdefault("data", {}).setdefault("cqg", {})["password"] = os.getenv("CQG_PASSWORD")
    if os.getenv("POLYGON_API_KEY"):
        cfg.setdefault("data", {}).setdefault("polygon", {})["api_key"] = os.getenv("POLYGON_API_KEY")
    return cfg
