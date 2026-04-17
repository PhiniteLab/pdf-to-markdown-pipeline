"""Shared utilities for the CortexMark."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from cortexmark.paths import (
    CONFIG_ENV_KEYS,
    MANIFEST_ENV_KEYS,
    SOURCE_ID_ENV_KEYS,
    PathSettings,
    build_path_settings,
    find_project_root,
    first_present,
    load_dotenv_values,
    merged_runtime_env,
    resolve_binary,
    resolve_manifest_file,
    resolve_portable_path,
)

PROJECT_ROOT = find_project_root()
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "pipeline.yaml"
DEFAULT_SOURCE_ID = "default"
ENGINE_ENV_KEYS: tuple[str, ...] = ("PIPELINE_ENGINE", "CORTEXMARK_ENGINE")

_CONFIG_CACHE: dict[str, Any] | None = None


def detect_device() -> str:
    """Return 'cuda' if a CUDA-capable GPU is available, otherwise 'cpu'."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


# ── Configuration and path settings ─────────────────────────────────────────


def runtime_environ(cfg: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Return merged runtime env (process env overrides .env) for the active project root."""
    project_root = (
        Path(str(cfg.get("__project_root__"))).resolve()
        if cfg and cfg.get("__project_root__")
        else find_project_root(start=Path.cwd())
    )
    return merged_runtime_env(project_root)


def runtime_env_value(*keys: str, cfg: Mapping[str, Any] | None = None) -> str | None:
    """Return the first configured runtime env value across process env and .env."""
    return first_present(runtime_environ(cfg), keys)


def _resolve_config_path(path: Path | None = None) -> tuple[Path, Path]:
    project_root = find_project_root(start=Path.cwd())
    merged_env = merged_runtime_env(project_root)

    if path is not None:
        config_path = resolve_portable_path(path, project_root=project_root, base_dir=Path.cwd(), environ=merged_env)
        return config_path, project_root

    env_value = first_present(merged_env, CONFIG_ENV_KEYS)
    if env_value:
        config_path = resolve_portable_path(
            env_value, project_root=project_root, base_dir=project_root, environ=merged_env
        )
        return config_path, project_root

    return (project_root / "configs" / "pipeline.yaml").resolve(), project_root


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load and cache the pipeline YAML configuration."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and path is None:
        return _CONFIG_CACHE

    config_path, project_root = _resolve_config_path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config must be a YAML mapping, got {type(cfg).__name__}")
    cfg.setdefault("__config_file__", str(config_path))
    cfg.setdefault("__config_dir__", str(config_path.parent))
    cfg.setdefault("__project_root__", str(project_root))
    if path is None:
        _CONFIG_CACHE = cfg
    return cfg


def reset_config_cache() -> None:
    """Clear cached config (useful for tests)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


def get_path_settings(cfg: Mapping[str, Any] | None = None) -> PathSettings:
    """Return the central path settings object for the current runtime."""
    project_root = Path(str(cfg.get("__project_root__"))).resolve() if cfg and cfg.get("__project_root__") else None
    return build_path_settings(cfg, project_root=project_root)


def resolve_path(raw: str | Path, *, base_dir: Path | str | None = None) -> Path:
    """Resolve a path relative to *base_dir* or the discovered project root."""
    settings = get_path_settings()
    return resolve_portable_path(
        raw, project_root=settings.project_root, base_dir=Path(base_dir) if base_dir is not None else None
    )


def resolve_relative_path(raw: str | Path, base_dir: Path | str | None = None) -> Path:
    """Resolve *raw* relative to *base_dir* when given, otherwise project root."""
    return resolve_path(raw, base_dir=Path(base_dir) if base_dir is not None else None)


def config_base_dir(cfg: Mapping[str, Any]) -> Path:
    """Return the directory of the loaded config when known."""
    raw = cfg.get("__config_dir__")
    if raw:
        return Path(str(raw)).resolve()
    return get_path_settings(cfg).config_dir


def get_source_id(cfg: Mapping[str, Any], *, default: str = DEFAULT_SOURCE_ID) -> str:
    """Return the generic source identifier used for default input/output scoping."""
    project_root = Path(str(cfg.get("__project_root__"))).resolve() if cfg.get("__project_root__") else None
    dotenv = load_dotenv_values(project_root or find_project_root())
    merged_env = {**dotenv, **os.environ}
    env_source = first_present(merged_env, SOURCE_ID_ENV_KEYS)
    if env_source:
        return env_source
    source_id = cfg.get("source_id")
    if source_id:
        return str(source_id)
    return default


def resolve_configured_path(cfg: Mapping[str, Any], key: str, fallback: str) -> Path:
    """Resolve a named config path using env/.env/config/default precedence."""
    settings = get_path_settings(cfg)
    mapping = {
        "data_raw": settings.raw_data_dir,
        "output_raw_md": settings.raw_md_dir,
        "output_cleaned_md": settings.cleaned_md_dir,
        "output_chunks": settings.chunks_dir,
        "output_quality": settings.quality_dir,
        "output_semantic_chunks": settings.semantic_chunks_dir,
    }
    if key in mapping:
        return mapping[key]

    paths = cfg.get("paths", {})
    raw = paths.get(key) if isinstance(paths, Mapping) else None
    if raw:
        return resolve_relative_path(str(raw), base_dir=config_base_dir(cfg))
    return resolve_relative_path(fallback, base_dir=settings.project_root)


def resolve_output_subdir(cfg: Mapping[str, Any], *parts: str) -> Path:
    """Resolve a path under the portable outputs root."""
    settings = get_path_settings(cfg)
    return (settings.outputs_dir.joinpath(*parts)).resolve()


def resolve_manifest_path(cfg: Mapping[str, Any], *, session_name: str | None = None) -> Path:
    """Return the manifest path with optional session scoping."""
    manifest_path = resolve_manifest_file(cfg, project_root=get_path_settings(cfg).project_root)
    if session_name:
        return (manifest_path.parent / f".manifest-{session_name}.json").resolve()
    return manifest_path.resolve()


def resolve_quality_dir(cfg: Mapping[str, Any], *, session_name: str | None = None) -> Path:
    """Return output quality directory, optionally scoped by session."""
    quality_dir = get_path_settings(cfg).quality_dir
    if session_name:
        quality_dir = quality_dir / session_name
    return quality_dir.resolve()


def resolve_quality_report_path(
    cfg: Mapping[str, Any],
    filename: str,
    *,
    session_name: str | None = None,
) -> Path:
    """Return a quality report output path with optional session scoping."""
    return (resolve_quality_dir(cfg, session_name=session_name) / filename).resolve()


def resolve_plugin_dir(cfg: Mapping[str, Any] | None = None) -> Path:
    """Return the plugin discovery directory."""
    return get_path_settings(cfg).plugin_dir.resolve()


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


__all__ = [
    "CONFIG_ENV_KEYS",
    "DEFAULT_CONFIG_PATH",
    "DEFAULT_SOURCE_ID",
    "ENGINE_ENV_KEYS",
    "MANIFEST_ENV_KEYS",
    "PROJECT_ROOT",
    "Manifest",
    "PathSettings",
    "config_base_dir",
    "detect_device",
    "file_hash",
    "find_project_root",
    "get_path_settings",
    "get_source_id",
    "load_config",
    "load_dotenv_values",
    "merged_runtime_env",
    "mirror_directory_tree",
    "reset_config_cache",
    "resolve_binary",
    "resolve_configured_path",
    "resolve_manifest_path",
    "resolve_output_subdir",
    "resolve_path",
    "resolve_plugin_dir",
    "resolve_portable_path",
    "resolve_quality_dir",
    "resolve_quality_report_path",
    "resolve_relative_path",
    "runtime_env_value",
    "runtime_environ",
    "setup_logging",
]
