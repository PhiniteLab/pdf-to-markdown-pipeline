from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.common import (
    Manifest,
    load_config,
    mirror_directory_tree,
    resolve_path,
    setup_logging,
)

PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s+)?\d+\s*$", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^\s*chapter\b[:\s-]*(.*)$", re.IGNORECASE)
SECTION_RE = re.compile(r"^\s*section\b[:\s-]*(.*)$", re.IGNORECASE)
COMBINED_HEADING_RE = re.compile(
    r"^\s*chapter\b[:\s-]*(.*?)\s+section\b[:\s-]*(.*)$",
    re.IGNORECASE,
)
TABLE_CELL_STRIP_RE = re.compile(r"\s{2,}")


def strip_markdown_heading(line: str) -> str:
    return re.sub(r"^\s*#{1,6}\s*", "", line).strip()


def normalize_heading_lines(line: str) -> list[str]:
    original = line.strip()
    stripped = strip_markdown_heading(line)
    if not stripped:
        return [""]

    combined_match = COMBINED_HEADING_RE.match(stripped)
    if combined_match:
        chapter_title = combined_match.group(1).strip() or "Chapter"
        section_title = combined_match.group(2).strip() or "Section"
        return [f"# {chapter_title}", f"## {section_title}"]

    chapter_match = CHAPTER_RE.match(stripped)
    if chapter_match:
        title = chapter_match.group(1).strip() or stripped
        return [f"# {title}" if title != stripped else f"# {stripped}"]

    section_match = SECTION_RE.match(stripped)
    if section_match:
        title = section_match.group(1).strip() or stripped
        return [f"## {title}" if title != stripped else f"## {stripped}"]

    if original.startswith("#"):
        return [original]

    return [stripped]


def remove_page_numbers(lines: list[str]) -> list[str]:
    return [line for line in lines if not PAGE_NUMBER_RE.match(line.strip())]


def remove_repeated_headers_footers(lines: list[str], *, min_count: int = 3, max_length: int = 80) -> list[str]:
    normalized = [line.strip() for line in lines if line.strip()]
    counts = Counter(normalized)
    repeated = {
        line
        for line, count in counts.items()
        if count >= min_count
        and len(line) <= max_length
        and not line.startswith("#")
        and not line.startswith("##")
        and not line.startswith("```")
        and not line.startswith(">")
    }
    return [line for line in lines if line.strip() not in repeated]


def fix_wrapped_lines(lines: list[str]) -> list[str]:
    rebuilt: list[str] = []
    paragraph: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        merged = paragraph[0]
        for fragment in paragraph[1:]:
            if merged.endswith("-") and fragment and fragment[0].islower():
                merged = merged[:-1] + fragment.lstrip()
            else:
                merged = merged.rstrip() + " " + fragment.lstrip()
        rebuilt.append(merged.strip())
        paragraph.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            rebuilt.append(stripped)
            in_code_block = not in_code_block
            continue
        if in_code_block:
            rebuilt.append(line)
            continue
        if not stripped:
            flush_paragraph()
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            rebuilt.append(stripped)
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            if rebuilt and rebuilt[-1] != "":
                rebuilt.append("")
            rebuilt.append(stripped)
            rebuilt.append("")
            continue
        paragraph.append(stripped)

    flush_paragraph()

    while rebuilt and rebuilt[-1] == "":
        rebuilt.pop()

    compact: list[str] = []
    for item in rebuilt:
        if item == "" and compact and compact[-1] == "":
            continue
        compact.append(item)
    return compact


def clean_markdown(text: str, *, min_repeated: int = 3, max_header_len: int = 80) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = remove_page_numbers(lines)
    lines = remove_repeated_headers_footers(lines, min_count=min_repeated, max_length=max_header_len)
    normalized_lines: list[str] = []
    for line in lines:
        normalized_lines.extend(normalize_heading_lines(line))
    cleaned_lines = fix_wrapped_lines(normalized_lines)
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = normalize_table_blocks(cleaned_text)
    return cleaned_text.strip() + "\n"


def normalize_table_cell(cell: str) -> str:
    """Collapse internal whitespace in a table cell."""
    return TABLE_CELL_STRIP_RE.sub(" ", cell.strip())


def normalize_table_blocks(text: str) -> str:
    """Normalize Markdown table blocks: trim cells, ensure separator alignment, remove empty tables."""
    result_lines: list[str] = []
    table_lines: list[str] = []
    in_table = False

    def flush_table() -> None:
        if not table_lines:
            return
        # Parse rows into cells
        rows: list[list[str]] = []
        for tl in table_lines:
            cells = [normalize_table_cell(c) for c in tl.strip().strip("|").split("|")]
            rows.append(cells)

        if not rows:
            return

        # Find separator row (all cells match ---+ pattern)
        sep_idx = None
        for i, row in enumerate(rows):
            if all(re.match(r"^:?-{1,}:?$", c.strip()) or c.strip() == "" for c in row):
                sep_idx = i
                break

        # If no separator found, look for header + data pattern and insert one
        if sep_idx is None and len(rows) >= 2:
            sep_idx = 1
            rows.insert(1, ["---"] * len(rows[0]))

        # Normalise column count
        col_count = max(len(r) for r in rows)
        for i, row in enumerate(rows):
            while len(row) < col_count:
                row.append("---" if (sep_idx is not None and i == sep_idx) else "")

        # Skip degenerate tables (only header + separator, no data)
        data_rows = [r for idx, r in enumerate(rows) if idx != sep_idx and idx != (sep_idx - 1 if sep_idx else -1)]
        non_empty_data = [r for r in data_rows if any(c.strip() for c in r)]
        if not non_empty_data:
            return

        # Rebuild
        for row in rows:
            result_lines.append("| " + " | ".join(row) + " |")

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(stripped)
        else:
            if in_table:
                flush_table()
                table_lines = []
                in_table = False
            result_lines.append(line)

    if in_table:
        flush_table()

    return "\n".join(result_lines)


def clean_file(input_path: Path, output_path: Path, *, cfg: dict[str, Any] | None = None) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input markdown not found: {input_path}")

    clean_cfg = (cfg or {}).get("clean", {})
    cleaned = clean_markdown(
        input_path.read_text(encoding="utf-8"),
        min_repeated=clean_cfg.get("min_repeated_header_count", 3),
        max_header_len=clean_cfg.get("max_repeated_header_length", 80),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(cleaned, encoding="utf-8")
    return output_path


def clean_tree(
    input_root: Path,
    output_root: Path,
    *,
    cfg: dict[str, Any] | None = None,
    manifest: Manifest | None = None,
) -> list[Path]:
    markdown_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not markdown_files:
        raise FileNotFoundError(f"No markdown files found under: {input_root}")

    mirror_directory_tree(input_root, output_root)
    written: list[Path] = []
    for markdown_path in markdown_files:
        if manifest and not manifest.needs_update(markdown_path):
            continue
        relative = markdown_path.relative_to(input_root)
        output_path = output_root / input_root.name / relative
        written.append(clean_file(markdown_path, output_path, cfg=cfg))
        if manifest:
            manifest.record(markdown_path)
    return written


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean raw Markdown extracted from PDF files.")
    parser.add_argument("--input", type=Path, help="Raw Markdown file or directory")
    parser.add_argument("--output-dir", type=Path, help="Root directory for cleaned Markdown output")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    parser.add_argument("--no-manifest", action="store_true", help="Disable idempotency manifest")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("clean", cfg)

    course_id = cfg.get("course_id", "mkt4822-RL")
    input_path = (args.input or resolve_path(cfg["paths"]["output_raw_md"]) / course_id).resolve()
    output_dir = (args.output_dir or resolve_path(cfg["paths"]["output_cleaned_md"])).resolve()

    manifest = None
    idem_cfg = cfg.get("idempotency", {})
    if idem_cfg.get("enabled", True) and not args.no_manifest:
        manifest = Manifest(resolve_path(idem_cfg.get("manifest_file", "outputs/.manifest.json")))

    try:
        if input_path.is_dir():
            written = clean_tree(input_path, output_dir, cfg=cfg, manifest=manifest)
            if manifest:
                manifest.save()
            log.info("cleaned %d markdown file(s) under %s", len(written), input_path)
            return 0

        output_path = output_dir / input_path.name
        written_path = clean_file(input_path, output_path, cfg=cfg)
        if manifest:
            manifest.record(input_path)
            manifest.save()
        log.info("wrote cleaned markdown to %s", written_path)
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid input: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
