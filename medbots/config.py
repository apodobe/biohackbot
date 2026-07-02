#!/usr/bin/env python3
"""Load bot_config.json and resolve feature flags (with env overrides)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "bot_config.json"

_DEFAULT_FEATURES: dict[str, bool] = {
    "ingest_telegram": False,
    "ingest_local_parsers": True,
    "grok_ingest_fallback": False,
    "apple_health": False,
    "genetics": True,
    "goals_reminders": True,
    "weekly_pending": False,
    "nutrition_import": True,
    "fitness_modules": False,
    "emias_chrome_download": False,
    "medsi_playwright": False,
    "research_briefs_keyboard": True,
    "legacy_flat_pdf_paths": False,
    "purge_foreign_records": True,
    "openfoodfacts_lookup": False,
    "food_log": False,
}


@dataclass
class BotConfig:
    bot_id: str
    patient_profile: str = "structured_database/PATIENT_PROFILE.json"
    corpus_path_env: str = "MEDBOTS_CORPUS_PATH"
    vps_corpus_path: str = ""
    features: dict[str, bool] = field(default_factory=dict)
    pipeline: dict[str, Any] = field(default_factory=dict)
    bot_root: Path = field(default_factory=Path.cwd)

    @classmethod
    def from_dict(cls, data: dict[str, Any], bot_root: Path) -> BotConfig:
        features = dict(_DEFAULT_FEATURES)
        features.update(data.get("features") or {})
        return cls(
            bot_id=str(data.get("bot_id") or "unknown"),
            patient_profile=str(
                data.get("patient_profile") or "structured_database/PATIENT_PROFILE.json"
            ),
            corpus_path_env=str(data.get("corpus_path_env") or "MEDBOTS_CORPUS_PATH"),
            vps_corpus_path=str(data.get("vps_corpus_path") or ""),
            features=features,
            pipeline=dict(data.get("pipeline") or {}),
            bot_root=bot_root.resolve(),
        )


def find_bot_root(start: Path | None = None) -> Path:
    """Walk up from *start* (or cwd) until bot_config.json is found."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / CONFIG_FILENAME).is_file():
            return candidate
    return cur


def load_config(bot_root: Path | None = None) -> BotConfig:
    root = (bot_root or find_bot_root()).resolve()
    path = root / CONFIG_FILENAME
    if not path.is_file():
        return BotConfig.from_dict({"bot_id": root.name}, root)
    data = json.loads(path.read_text(encoding="utf-8"))
    return BotConfig.from_dict(data, root)


def feature_enabled(name: str, config: BotConfig) -> bool:
    env_key = f"MEDBOTS_FEATURE_{name.upper()}"
    raw = os.environ.get(env_key, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return bool(config.features.get(name, _DEFAULT_FEATURES.get(name, False)))


def corpus_from_config(config: BotConfig) -> Path:
    from medbots.corpus_io import resolve_corpus

    env_name = config.corpus_path_env
    env_val = os.environ.get(env_name, "").strip()
    if env_val:
        return resolve_corpus(env_val)
    default = config.bot_root / "structured_database"
    return resolve_corpus(default)
