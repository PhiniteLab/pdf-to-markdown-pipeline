from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from cortexmark.common import (
    Manifest,
    get_source_id,
    load_config,
    mirror_directory_tree,
    resolve_configured_path,
    resolve_manifest_path,
    setup_logging,
)

# Default split levels match original behaviour (#, ##)
DEFAULT_SPLIT_LEVELS: list[int] = [1, 2]


def build_heading_re(split_levels: list[int] | None = None) -> re.Pattern[str]:
    """Build a heading regex that matches the given heading levels."""
    levels = split_levels or DEFAULT_SPLIT_LEVELS
    alts = "|".join(f"#{{{n}}}" for n in sorted(levels))
    return re.compile(rf"^({alts})\s+(.*\S)\s*$")


@dataclass
class Chunk:
    chapter: str | None = None
    section: str | None = None
    body: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.section or self.chapter or "untitled"

    def render(self) -> str:
        parts: list[str] = []
        if self.chapter:
            parts.append(f"# {self.chapter}")
        if self.section:
            parts.append(f"## {self.section}")
        if parts:
            parts.append("")
        parts.extend(self.body)
        return "\n".join(parts).strip() + "\n"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def parse_chunks(text: str, *, split_levels: list[int] | None = None) -> list[Chunk]:
    heading_re = build_heading_re(split_levels)
    levels = sorted(split_levels or DEFAULT_SPLIT_LEVELS)
    min_level = levels[0] if levels else 1

    chapter: str | None = None
    section: str | None = None
    body: list[str] = []
    chunks: list[Chunk] = []

    def flush() -> None:
        nonlocal body
        content = [line for line in body if line.strip()]
        if content:
            chunks.append(Chunk(chapter=chapter, section=section, body=content))
        body = []

    for raw_line in text.splitlines():
        match = heading_re.match(raw_line.strip())
        if not match:
            body.append(raw_line.rstrip())
            continue

        level_str, title = match.groups()
        level = len(level_str)
        if level == min_level:
            flush()
            chapter = title.strip()
            section = None
            continue
        # Any deeper split level becomes a section
        flush()
        section = title.strip()

    flush()
    return [chunk for chunk in chunks if chunk.body or chunk.section or chunk.chapter]


def chunk_file(input_path: Path, output_dir: Path, *, split_levels: list[int] | None = None) -> list[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"Cleaned markdown not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    chunks = parse_chunks(text, split_levels=split_levels)
    if not chunks:
        raise ValueError(f"No logical chunks could be produced from: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        path = output_dir / f"chunk_{index:03d}_{slugify(chunk.title)}.md"
        path.write_text(chunk.render(), encoding="utf-8")
        written.append(path)
    return written


def chunk_tree(
    input_root: Path,
    output_root: Path,
    *,
    manifest: Manifest | None = None,
    split_levels: list[int] | None = None,
) -> list[Path]:
    markdown_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not markdown_files:
        raise FileNotFoundError(f"No cleaned markdown files found under: {input_root}")

    mirror_directory_tree(input_root, output_root)
    written: list[Path] = []
    for markdown_path in markdown_files:
        if manifest and not manifest.needs_update(markdown_path):
            continue
        relative = markdown_path.relative_to(input_root)
        target_dir = output_root / input_root.name / relative.parent / markdown_path.stem
        written.extend(chunk_file(markdown_path, target_dir, split_levels=split_levels))
        if manifest:
            manifest.record(markdown_path)
    return written


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Split cleaned Markdown into logical chapter/section chunks.")
    parser.add_argument("--input", type=Path, help="Cleaned Markdown file or directory")
    parser.add_argument("--output-dir", type=Path, help="Chunk output root directory")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    parser.add_argument("--no-manifest", action="store_true", help="Disable idempotency manifest")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("chunk", cfg)

    chunk_cfg = cfg.get("chunk", {})
    split_levels = chunk_cfg.get("split_levels", DEFAULT_SPLIT_LEVELS)

    source_id = get_source_id(cfg)
    input_path = (
        args.input or resolve_configured_path(cfg, "output_cleaned_md", "outputs/cleaned_md") / source_id
    ).resolve()
    output_dir = (args.output_dir or resolve_configured_path(cfg, "output_chunks", "outputs/chunks")).resolve()

    manifest = None
    idem_cfg = cfg.get("idempotency", {})
    if idem_cfg.get("enabled", True) and not args.no_manifest:
        manifest = Manifest(resolve_manifest_path(cfg))

    try:
        if input_path.is_dir():
            chunk_paths = chunk_tree(input_path, output_dir, manifest=manifest, split_levels=split_levels)
            if manifest:
                manifest.save()
            log.info("wrote %d chunk(s) for markdown files under %s", len(chunk_paths), input_path)
            return 0

        chunk_paths = chunk_file(input_path, output_dir / input_path.stem, split_levels=split_levels)
        if manifest:
            manifest.record(input_path)
            manifest.save()
        log.info("wrote %d chunk(s) to %s", len(chunk_paths), output_dir / input_path.stem)
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid input: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
