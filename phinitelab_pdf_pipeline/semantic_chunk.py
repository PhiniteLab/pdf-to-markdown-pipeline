"""Semantic-aware chunking for scientific and mathematical documents.

Extends heading-based chunking with recognition of:
  - Theorem / Lemma / Proposition / Corollary blocks
  - Proof blocks (with QED detection)
  - Definition / Assumption / Remark / Example blocks
  - Algorithm blocks (code-fenced or keyword-detected)
  - Equation labels and internal cross-references

Each chunk carries an ``entity_type`` that downstream consumers (RAG export,
QA, search) can use to filter or weight results.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from phinitelab_pdf_pipeline.common import (
    Manifest,
    load_config,
    mirror_directory_tree,
    resolve_path,
    setup_logging,
)

# ── Entity types ─────────────────────────────────────────────────────────────

ENTITY_THEOREM = "theorem"
ENTITY_PROOF = "proof"
ENTITY_DEFINITION = "definition"
ENTITY_ALGORITHM = "algorithm"
ENTITY_EXAMPLE = "example"
ENTITY_REMARK = "remark"
ENTITY_NARRATIVE = "narrative"

ALL_ENTITY_TYPES: tuple[str, ...] = (
    ENTITY_THEOREM,
    ENTITY_PROOF,
    ENTITY_DEFINITION,
    ENTITY_ALGORITHM,
    ENTITY_EXAMPLE,
    ENTITY_REMARK,
    ENTITY_NARRATIVE,
)

# ── Patterns ─────────────────────────────────────────────────────────────────

# Theorem-like environments: "Theorem 3.2", "Lemma 1", "Corollary 2.1 (Name)"
_THEOREM_LIKE = (
    "theorem",
    "lemma",
    "proposition",
    "corollary",
)

# Definition-like environments
_DEFINITION_LIKE = (
    "definition",
    "assumption",
    "axiom",
    "conjecture",
    "hypothesis",
    "condition",
)

_EXAMPLE_LIKE = (
    "example",
    "exercise",
    "problem",
    "case",
)

_REMARK_LIKE = (
    "remark",
    "note",
    "observation",
    "comment",
    "convention",
)

# Build combined pattern for block openers
_ALL_ENV_NAMES = _THEOREM_LIKE + _DEFINITION_LIKE + _EXAMPLE_LIKE + _REMARK_LIKE
_ENV_ALTS = "|".join(re.escape(n) for n in _ALL_ENV_NAMES)

# Matches: "**Theorem 3.2.**", "**Theorem 3.2 (Bellman)**", "Theorem 3.2.",
# "**Definition 1:**", "THEOREM 2.1", "Lemma.", etc.
BLOCK_OPENER_RE = re.compile(
    rf"^(?:\*\*)?(?P<kind>{_ENV_ALTS})"  # bold-optional + kind
    rf"(?:\s+(?P<label>[\d]+(?:\.[\d]+)*))?\.?"  # optional numeric label
    rf"(?:\s*\((?P<name>[^)]+)\))?"  # optional parenthesized name
    rf"[.:)]*(?:\*\*)?\s*(?P<rest>.*)$",  # trailing punctuation + rest
    re.IGNORECASE,
)

# Proof opener: "Proof.", "Proof:", "**Proof.**", "Proof of Theorem 3.2."
PROOF_OPENER_RE = re.compile(
    r"^(?:\*\*)?[Pp]roof"
    r"(?:\s+of\s+(?P<of_label>\w[\w\s.]*\d[\d.]*))?\.?"
    r"[.:)]*(?:\*\*)?\s*(?P<rest>.*)$",
)

# QED markers signalling end of a proof
QED_MARKERS: tuple[str, ...] = ("□", "∎", "■", "q.e.d.", "qed", "▪", "◻")

# Algorithm detection: code fence with "algorithm" or keyword-based
ALGORITHM_FENCE_RE = re.compile(r"^```(?:text|algorithm|pseudocode)?\s*$", re.IGNORECASE)
ALGORITHM_LABEL_RE = re.compile(
    r"^(?:\*\*)?(?:Algorithm)\s+(?P<label>[\d]+(?:\.[\d]+)*)[.:)]*(?:\*\*)?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

# Inline formula detection (for metadata)
DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
INLINE_MATH_RE = re.compile(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)")

# Cross-reference patterns
CROSS_REF_RE = re.compile(
    r"(?:Equation|Eq\.|Figure|Fig\.|Table|Theorem|Lemma|Definition|"
    r"Proposition|Corollary|Algorithm|Section|Sec\.|Chapter|Ch\.)"
    r"\s*[\(]?([\d]+(?:\.[\d]+)*)[\)]?",
    re.IGNORECASE,
)

# Heading pattern (reused from chunk.py logic)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class SemanticChunk:
    """A chunk with scientific entity metadata."""

    chapter: str | None = None
    section: str | None = None
    body: list[str] = field(default_factory=list)
    entity_type: str = ENTITY_NARRATIVE
    entity_label: str | None = None  # e.g. "Theorem 3.2"
    entity_name: str | None = None  # e.g. "Bellman Optimality"
    parent_label: str | None = None  # proof → parent theorem label
    formulas: list[str] = field(default_factory=list)
    cross_refs: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        if self.entity_label:
            name_suffix = f" ({self.entity_name})" if self.entity_name else ""
            return f"{self.entity_label}{name_suffix}"
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


# ── Extraction helpers ───────────────────────────────────────────────────────


def classify_env_kind(kind: str) -> str:
    """Map an environment name to an entity type."""
    kind_lower = kind.lower()
    if kind_lower in _THEOREM_LIKE:
        return ENTITY_THEOREM
    if kind_lower in _DEFINITION_LIKE:
        return ENTITY_DEFINITION
    if kind_lower in _EXAMPLE_LIKE:
        return ENTITY_EXAMPLE
    if kind_lower in _REMARK_LIKE:
        return ENTITY_REMARK
    return ENTITY_NARRATIVE


def extract_formulas(text: str) -> list[str]:
    """Extract display and inline math from text."""
    formulas: list[str] = []
    for m in DISPLAY_MATH_RE.finditer(text):
        formulas.append(m.group(1).strip())
    for m in INLINE_MATH_RE.finditer(text):
        formulas.append(m.group(1).strip())
    return formulas


def extract_cross_refs(text: str) -> list[str]:
    """Extract cross-reference labels from text (e.g. 'Theorem 3.2')."""
    refs: list[str] = []
    for m in CROSS_REF_RE.finditer(text):
        full = m.group(0).strip().rstrip(")")
        if full not in refs:
            refs.append(full)
    return refs


def has_qed(line: str) -> bool:
    """Check if a line ends with a QED marker."""
    stripped = line.rstrip()
    lower = stripped.lower()
    return any(lower.endswith(marker) for marker in QED_MARKERS)


def _slugify(value: str) -> str:
    """URL-safe slug from a title string."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


# ── Core parser ──────────────────────────────────────────────────────────────


def parse_semantic_chunks(
    text: str,
    *,
    split_on_headings: bool = True,
    heading_levels: list[int] | None = None,
) -> list[SemanticChunk]:
    """Parse text into semantic chunks aware of scientific environments.

    Recognises theorem/proof/definition/algorithm blocks and assigns
    ``entity_type`` accordingly.  Falls back to heading-based splitting
    for narrative content.
    """
    levels = heading_levels or [1, 2]
    min_level = min(levels) if levels else 1

    chunks: list[SemanticChunk] = []
    chapter: str | None = None
    section: str | None = None

    # Accumulator for the current chunk
    body: list[str] = []
    entity_type: str = ENTITY_NARRATIVE
    entity_label: str | None = None
    entity_name: str | None = None
    parent_label: str | None = None
    last_theorem_label: str | None = None

    in_code_fence = False
    in_proof = False

    def flush() -> None:
        nonlocal body, entity_type, entity_label, entity_name, parent_label
        content = [line for line in body if line.strip()]
        if content:
            full_text = "\n".join(content)
            chunks.append(
                SemanticChunk(
                    chapter=chapter,
                    section=section,
                    body=content,
                    entity_type=entity_type,
                    entity_label=entity_label,
                    entity_name=entity_name,
                    parent_label=parent_label,
                    formulas=extract_formulas(full_text),
                    cross_refs=extract_cross_refs(full_text),
                )
            )
        body = []
        entity_type = ENTITY_NARRATIVE
        entity_label = None
        entity_name = None
        parent_label = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        # Track code fences to avoid false matches inside them
        if stripped.startswith("```"):
            if in_code_fence:
                # Closing fence
                in_code_fence = False
                body.append(line)
                # If this was an algorithm block, flush after close
                if entity_type == ENTITY_ALGORITHM:
                    flush()
                continue
            # Opening fence — check if it's an algorithm fence
            in_code_fence = True
            if ALGORITHM_FENCE_RE.match(stripped) and entity_type != ENTITY_ALGORITHM:
                flush()
                entity_type = ENTITY_ALGORITHM
            body.append(line)
            continue

        if in_code_fence:
            body.append(line)
            continue

        # ── Heading detection ────────────────────────────────────────
        if split_on_headings:
            heading_match = HEADING_RE.match(stripped)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                if level in levels:
                    # Flush any in-progress block
                    if in_proof:
                        in_proof = False
                    flush()
                    if level == min_level:
                        chapter = title
                        section = None
                    else:
                        section = title
                    continue

        # ── Proof opener ─────────────────────────────────────────────
        proof_match = PROOF_OPENER_RE.match(stripped)
        if proof_match and not in_proof:
            flush()
            entity_type = ENTITY_PROOF
            of_label = proof_match.group("of_label")
            if of_label:
                parent_label = of_label.strip()
            elif last_theorem_label:
                parent_label = last_theorem_label
            in_proof = True
            rest = proof_match.group("rest")
            if rest:
                body.append(rest)
            continue

        # ── QED detection (end of proof) ─────────────────────────────
        if in_proof and has_qed(stripped):
            body.append(line)
            in_proof = False
            flush()
            continue

        # ── Block opener (theorem, definition, etc.) ─────────────────
        block_match = BLOCK_OPENER_RE.match(stripped)
        if block_match:
            kind = block_match.group("kind")
            label = block_match.group("label")
            name = block_match.group("name")
            rest = block_match.group("rest")

            new_type = classify_env_kind(kind)
            full_label = f"{kind.capitalize()} {label}" if label else kind.capitalize()

            # Flush previous block
            flush()
            entity_type = new_type
            entity_label = full_label
            entity_name = name
            if new_type == ENTITY_THEOREM:
                last_theorem_label = full_label
            if rest:
                body.append(rest)
            continue

        # ── Algorithm label line ─────────────────────────────────────
        algo_match = ALGORITHM_LABEL_RE.match(stripped)
        if algo_match:
            flush()
            entity_type = ENTITY_ALGORITHM
            entity_label = f"Algorithm {algo_match.group('label')}"
            rest = algo_match.group("rest")
            if rest:
                body.append(rest)
            continue

        # ── Regular line ─────────────────────────────────────────────
        body.append(line)

    # Flush remaining
    if in_proof:
        in_proof = False
    flush()

    return [c for c in chunks if c.body or c.entity_label]


# ── File / tree operations ───────────────────────────────────────────────────


def chunk_file(
    input_path: Path,
    output_dir: Path,
    *,
    heading_levels: list[int] | None = None,
) -> list[Path]:
    """Parse a file into semantic chunks and write numbered output files."""
    if not input_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    chunks = parse_semantic_chunks(text, heading_levels=heading_levels)
    if not chunks:
        raise ValueError(f"No semantic chunks could be produced from: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        slug = _slugify(chunk.title)
        path = output_dir / f"chunk_{index:03d}_{slug}.md"
        path.write_text(chunk.render(), encoding="utf-8")
        written.append(path)
    return written


def chunk_tree(
    input_root: Path,
    output_root: Path,
    *,
    manifest: Manifest | None = None,
    heading_levels: list[int] | None = None,
) -> list[Path]:
    """Semantically chunk all Markdown files in a directory tree."""
    markdown_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not markdown_files:
        raise FileNotFoundError(f"No markdown files found under: {input_root}")

    mirror_directory_tree(input_root, output_root)
    written: list[Path] = []
    for markdown_path in markdown_files:
        if manifest and not manifest.needs_update(markdown_path):
            continue
        relative = markdown_path.relative_to(input_root)
        target_dir = output_root / input_root.name / relative.parent / markdown_path.stem
        written.extend(chunk_file(markdown_path, target_dir, heading_levels=heading_levels))
        if manifest:
            manifest.record(markdown_path)
    return written


# ── Metadata export ──────────────────────────────────────────────────────────


def chunks_to_records(chunks: list[SemanticChunk], source: str) -> list[dict[str, object]]:
    """Convert semantic chunks to metadata-rich dictionaries for export."""
    records: list[dict[str, object]] = []
    for i, chunk in enumerate(chunks):
        records.append(
            {
                "index": i,
                "source": source,
                "title": chunk.title,
                "entity_type": chunk.entity_type,
                "entity_label": chunk.entity_label,
                "entity_name": chunk.entity_name,
                "parent_label": chunk.parent_label,
                "formulas": chunk.formulas,
                "cross_refs": chunk.cross_refs,
                "chapter": chunk.chapter,
                "section": chunk.section,
                "line_count": len(chunk.body),
            }
        )
    return records


def build_entity_summary(chunks: list[SemanticChunk]) -> dict[str, int]:
    """Count chunks by entity type."""
    summary: dict[str, int] = {}
    for chunk in chunks:
        summary[chunk.entity_type] = summary.get(chunk.entity_type, 0) + 1
    return summary


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Semantic chunking for scientific Markdown: recognises theorems, proofs, definitions, algorithms."
    )
    parser.add_argument("--input", type=Path, help="Markdown file or directory")
    parser.add_argument("--output-dir", type=Path, help="Chunk output root directory")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    parser.add_argument("--no-manifest", action="store_true", help="Disable idempotency manifest")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("semantic_chunk", cfg)

    chunk_cfg = cfg.get("chunk", {})
    heading_levels = chunk_cfg.get("split_levels", [1, 2])

    course_id = cfg.get("course_id", "mkt4822-RL")
    input_path = (args.input or resolve_path(cfg["paths"]["output_cleaned_md"]) / course_id).resolve()
    output_dir = (args.output_dir or resolve_path(cfg["paths"]["output_chunks"])).resolve()

    manifest = None
    idem_cfg = cfg.get("idempotency", {})
    if idem_cfg.get("enabled", True) and not args.no_manifest:
        manifest = Manifest(resolve_path(idem_cfg.get("manifest_file", "outputs/.manifest.json")))

    try:
        if input_path.is_dir():
            written = chunk_tree(input_path, output_dir, manifest=manifest, heading_levels=heading_levels)
            if manifest:
                manifest.save()
            log.info("wrote %d semantic chunk(s) from %s", len(written), input_path)
        else:
            written = chunk_file(input_path, output_dir / input_path.stem, heading_levels=heading_levels)
            if manifest:
                manifest.record(input_path)
                manifest.save()
            log.info("wrote %d semantic chunk(s) to %s", len(written), output_dir / input_path.stem)
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid input: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
