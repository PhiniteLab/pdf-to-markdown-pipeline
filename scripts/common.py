"""Shared utilities for the pdf-to-markdown pipeline."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "pipeline.yaml"

_config_cache: dict[str, Any] | None = None


# ── Configuration ────────────────────────────────────────────────────────────


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and cache the pipeline YAML configuration."""
    global _config_cache
    if _config_cache is not None and path is None:
        return _config_cache
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config must be a YAML mapping, got {type(cfg).__name__}")
    if path is None:
        _config_cache = cfg
    return cfg


def reset_config_cache() -> None:
    """Clear cached config (useful for tests)."""
    global _config_cache
    _config_cache = None


def resolve_path(raw: str) -> Path:
    """Resolve a config path relative to the project root."""
    p = Path(raw)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


# ── Logging ──────────────────────────────────────────────────────────────────


def setup_logging(name: str, cfg: dict[str, Any] | None = None) -> logging.Logger:
    """Create a configured logger for a pipeline script."""
    log_cfg = (cfg or {}).get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
    fmt = log_cfg.get("format", "%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    datefmt = log_cfg.get("date_format", "%Y-%m-%d %H:%M:%S")

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        logger.addHandler(handler)
    return logger


# ── File-system helpers ──────────────────────────────────────────────────────


def mirror_directory_tree(input_root: Path, output_root: Path) -> Path:
    """Replicate the directory tree of *input_root* under *output_root*.

    Returns the created target root (``output_root / input_root.name``).
    """
    target_root = output_root / input_root.name
    target_root.mkdir(parents=True, exist_ok=True)
    for directory in sorted(p for p in input_root.rglob("*") if p.is_dir()):
        (target_root / directory.relative_to(input_root)).mkdir(parents=True, exist_ok=True)
    return target_root


def file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Manifest (idempotency) ──────────────────────────────────────────────────


class Manifest:
    """Track source→output hashes so unchanged files can be skipped."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, str] = {}
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                self._data = json.load(fh)

    def needs_update(self, source: Path) -> bool:
        """Return True when *source* has no record or its hash changed."""
        key = str(source)
        current_hash = file_hash(source)
        return self._data.get(key) != current_hash

    def record(self, source: Path) -> None:
        """Store the current hash of *source*."""
        self._data[str(source)] = file_hash(source)

    def save(self) -> None:
        """Persist the manifest to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)
            fh.write("\n")
