"""RAG-ready export: convert chunks to embedding-friendly JSON Lines.

Each output record contains:
  - id: unique chunk identifier
  - source: original file path
  - title: chunk heading
  - text: chunk body text
  - metadata: chapter, section, token estimate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from scripts.common import load_config, resolve_path, setup_logging

# ── Data structures ──────────────────────────────────────────────────────────

WHITESPACE_RUN_RE = re.compile(r"\s+")


@dataclass
class RAGRecord:
    """Single embedding-ready record."""

    id: str
    source: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def make_chunk_id(source: str, title: str, index: int) -> str:
    """Deterministic chunk ID from source + title + index."""
    raw = f"{source}::{title}::{index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def parse_chunk_file(file_path: Path) -> RAGRecord:
    """Parse a single chunk Markdown file into a RAGRecord."""
    text = file_path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")

    title = ""
    chapter = ""
    section = ""
    body_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not chapter:
            chapter = stripped.lstrip("# ").strip()
            continue
        if stripped.startswith("## ") and not section:
            section = stripped.lstrip("# ").strip()
            continue
        body_lines.append(stripped)

    title = section or chapter or file_path.stem
    body_text = "\n".join(line for line in body_lines if line).strip()

    return RAGRecord(
        id=make_chunk_id(str(file_path), title, 0),
        source=str(file_path),
        title=title,
        text=body_text,
        metadata={
            "chapter": chapter,
            "section": section,
            "token_estimate": estimate_tokens(body_text),
        },
    )


def normalize_text_for_embedding(text: str) -> str:
    """Clean text for embedding: collapse whitespace, strip control chars."""
    cleaned = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return WHITESPACE_RUN_RE.sub(" ", cleaned).strip()


# ── Export functions ─────────────────────────────────────────────────────────


def export_file(file_path: Path, *, normalize: bool = True) -> RAGRecord:
    """Export a single chunk file as a RAGRecord."""
    if not file_path.exists():
        raise FileNotFoundError(f"Chunk file not found: {file_path}")
    record = parse_chunk_file(file_path)
    if normalize:
        record.text = normalize_text_for_embedding(record.text)
        record.metadata["token_estimate"] = estimate_tokens(record.text)
    return record


def export_tree(input_root: Path, *, normalize: bool = True) -> list[RAGRecord]:
    """Export all chunk files under a directory tree."""
    md_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not md_files:
        raise FileNotFoundError(f"No chunk files found under: {input_root}")
    return [export_file(f, normalize=normalize) for f in md_files]


def write_jsonl(records: list[RAGRecord], output_path: Path) -> Path:
    """Write records as JSON Lines (one JSON object per line)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for record in records:
            line = json.dumps(asdict(record), ensure_ascii=False)
            fh.write(line + "\n")
    return output_path


def write_json_array(records: list[RAGRecord], output_path: Path) -> Path:
    """Write records as a JSON array (for smaller datasets)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(r) for r in records]
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def build_summary(records: list[RAGRecord]) -> dict[str, Any]:
    """Build a summary of the RAG export."""
    total_tokens = sum(r.metadata.get("token_estimate", 0) for r in records)
    return {
        "total_records": len(records),
        "total_tokens_estimate": total_tokens,
        "avg_tokens_per_record": round(total_tokens / max(len(records), 1)),
        "sources": len({r.source for r in records}),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export chunks as RAG-ready JSON Lines for embedding pipelines.")
    parser.add_argument("--input", type=Path, help="Chunk file or directory to export")
    parser.add_argument("--output", type=Path, help="Output path for JSONL file")
    parser.add_argument(
        "--format",
        choices=["jsonl", "json"],
        default="jsonl",
        help="Output format (default: jsonl)",
    )
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="Skip text normalization for embedding",
    )
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("rag_export", cfg)

    input_path = (args.input or resolve_path(cfg["paths"]["output_chunks"])).resolve()
    default_ext = ".jsonl" if args.format == "jsonl" else ".json"
    output_path = (args.output or resolve_path(f"outputs/rag/chunks{default_ext}")).resolve()

    normalize = not args.no_normalize

    try:
        if input_path.is_dir():
            records = export_tree(input_path, normalize=normalize)
        else:
            records = [export_file(input_path, normalize=normalize)]

        if args.format == "jsonl":
            written = write_jsonl(records, output_path)
        else:
            written = write_json_array(records, output_path)

        summary = build_summary(records)
        log.info(
            "exported %d record(s), ~%d tokens → %s",
            summary["total_records"],
            summary["total_tokens_estimate"],
            written,
        )

    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
