"""Citation graph extraction and analysis from Markdown documents.

Scans converted Markdown for citation patterns and builds:
  - A list of extracted references
  - A citation graph (who cites whom)
  - Co-citation clusters
  - JSON and DOT (Graphviz) output

Works on already-converted Markdown (post-convert stage).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cortexmark.common import load_config, resolve_path, setup_logging

# ── Patterns ─────────────────────────────────────────────────────────────────

# Inline citation patterns: (Author, Year), (Author et al., Year), [1], [1,2,3]
PAREN_CITE_RE = re.compile(
    r"\(([A-Z][a-z]+(?:\s+(?:et\s+al\.?|(?:and|&)\s+[A-Z][a-z]+))?,?\s*\d{4}(?:;\s*[A-Z][a-z]+(?:\s+(?:et\s+al\.?|(?:and|&)\s+[A-Z][a-z]+))?,?\s*\d{4})*)\)"
)
BRACKET_CITE_RE = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")

# Reference list patterns
REF_NUMBERED_RE = re.compile(r"^\[(\d+)\]\s+(.+)")
REF_AUTHOR_YEAR_RE = re.compile(
    r"^([A-Z][a-z]+(?:,?\s+(?:and|&)\s+[A-Z][a-z]+|(?:\s+et\s+al\.?))?)\s*\((\d{4})\)[.,]?\s*(.+)"
)

# DOI in reference
DOI_IN_REF_RE = re.compile(r"(10\.\d{4,9}/[^\s,;\"')\]]+)")


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class Citation:
    """A single inline citation occurrence."""

    raw_text: str
    source_file: str = ""
    line_number: int = 0
    cite_type: str = ""  # "author-year" or "numeric"


@dataclass
class Reference:
    """A reference entry from the bibliography/references section."""

    key: str  # e.g. "Smith2020" or "1"
    raw_text: str
    authors: str = ""
    year: str = ""
    title: str = ""
    doi: str = ""


@dataclass
class CitationEdge:
    """An edge in the citation graph: document cites reference."""

    source_doc: str
    target_ref: str


@dataclass
class CitationGraph:
    """Complete citation analysis for a document or collection."""

    citations: list[Citation] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    edges: list[CitationEdge] = field(default_factory=list)
    top_cited: list[tuple[str, int]] = field(default_factory=list)


# ── Extraction engine ────────────────────────────────────────────────────────


def extract_inline_citations(text: str, source_file: str = "") -> list[Citation]:
    """Extract inline citations from text."""
    citations: list[Citation] = []
    lines = text.split("\n")

    for line_num, line in enumerate(lines, start=1):
        # Author-year pattern: (Smith, 2020)
        for match in PAREN_CITE_RE.finditer(line):
            citations.append(
                Citation(
                    raw_text=match.group(1).strip(),
                    source_file=source_file,
                    line_number=line_num,
                    cite_type="author-year",
                )
            )

        # Numeric pattern: [1], [1,2,3]
        for match in BRACKET_CITE_RE.finditer(line):
            # Skip if this looks like a Markdown link rather than a citation
            start = match.start()
            if start > 0 and line[start - 1] == "]":
                continue
            citations.append(
                Citation(
                    raw_text=match.group(1).strip(),
                    source_file=source_file,
                    line_number=line_num,
                    cite_type="numeric",
                )
            )

    return citations


def extract_references(text: str) -> list[Reference]:
    """Extract reference entries from the bibliography section."""
    refs: list[Reference] = []
    lines = text.split("\n")

    # Find the references section
    ref_start = -1
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped in (
            "# references",
            "## references",
            "### references",
            "# bibliography",
            "## bibliography",
            "**references**",
        ):
            ref_start = i + 1
            break

    if ref_start < 0:
        return refs

    for line in lines[ref_start:]:
        stripped = line.strip()
        if not stripped:
            continue
        # Stop at next section
        if stripped.startswith("#"):
            break

        # Numbered reference: [1] Author et al. (2020). Title...
        m = REF_NUMBERED_RE.match(stripped)
        if m:
            key = m.group(1)
            raw = m.group(2)
            doi_m = DOI_IN_REF_RE.search(raw)
            refs.append(
                Reference(
                    key=key,
                    raw_text=raw,
                    doi=doi_m.group(1) if doi_m else "",
                )
            )
            continue

        # Author-year reference: Smith (2020). Title...
        m = REF_AUTHOR_YEAR_RE.match(stripped)
        if m:
            authors = m.group(1)
            year = m.group(2)
            rest = m.group(3)
            key = f"{authors.split()[0]}{year}"
            doi_m = DOI_IN_REF_RE.search(rest)
            refs.append(
                Reference(
                    key=key,
                    raw_text=stripped,
                    authors=authors,
                    year=year,
                    title=rest.split(".")[0] if "." in rest else rest,
                    doi=doi_m.group(1) if doi_m else "",
                )
            )
            continue

    return refs


def build_citation_graph(
    citations: list[Citation],
    references: list[Reference],
    source_doc: str = "",
) -> CitationGraph:
    """Build a citation graph from extracted citations and references."""
    edges: list[CitationEdge] = []
    ref_counter: Counter[str] = Counter()

    for cite in citations:
        if cite.cite_type == "numeric":
            for num in re.findall(r"\d+", cite.raw_text):
                edges.append(CitationEdge(source_doc=source_doc, target_ref=num))
                ref_counter[num] += 1
        else:
            key = cite.raw_text.split(",")[0].strip()
            edges.append(CitationEdge(source_doc=source_doc, target_ref=key))
            ref_counter[key] += 1

    top_cited = ref_counter.most_common(20)

    return CitationGraph(
        citations=citations,
        references=references,
        edges=edges,
        top_cited=top_cited,
    )


# ── File / tree operations ───────────────────────────────────────────────────


def analyze_file(file_path: Path) -> CitationGraph:
    """Analyze citations in a single Markdown file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    citations = extract_inline_citations(text, source_file=str(file_path))
    references = extract_references(text)
    return build_citation_graph(citations, references, source_doc=str(file_path))


def analyze_tree(input_root: Path) -> CitationGraph:
    """Analyze citations across all Markdown files in a directory."""
    md_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not md_files:
        raise FileNotFoundError(f"No markdown files found under: {input_root}")

    all_citations: list[Citation] = []
    all_references: list[Reference] = []

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        all_citations.extend(extract_inline_citations(text, source_file=str(md_path)))
        all_references.extend(extract_references(text))

    return build_citation_graph(all_citations, all_references, source_doc=str(input_root))


# ── Output writers ───────────────────────────────────────────────────────────


def write_citation_report(graph: CitationGraph, output_path: Path) -> Path:
    """Write citation graph as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "summary": {
            "total_citations": len(graph.citations),
            "total_references": len(graph.references),
            "total_edges": len(graph.edges),
            "top_cited": graph.top_cited,
        },
        "citations": [asdict(c) for c in graph.citations],
        "references": [asdict(r) for r in graph.references],
        "edges": [asdict(e) for e in graph.edges],
    }
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def write_dot_graph(graph: CitationGraph, output_path: Path) -> Path:
    """Write citation graph in Graphviz DOT format."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["digraph citations {", "    rankdir=LR;", "    node [shape=box];"]

    seen_edges: set[tuple[str, str]] = set()
    for edge in graph.edges:
        src = edge.source_doc.replace('"', '\\"')
        tgt = edge.target_ref.replace('"', '\\"')
        pair = (src, tgt)
        if pair not in seen_edges:
            lines.append(f'    "{src}" -> "{tgt}";')
            seen_edges.add(pair)

    lines.append("}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract and analyze citations from Markdown files.")
    parser.add_argument("--input", type=Path, help="Markdown file or directory")
    parser.add_argument("--output", type=Path, help="Path for citation report (JSON)")
    parser.add_argument("--dot", type=Path, help="Path for DOT graph output")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("citations", cfg)

    input_path = (args.input or resolve_path(cfg["paths"]["output_raw_md"])).resolve()
    output_path = (args.output or resolve_path("outputs/quality/citations.json")).resolve()

    try:
        graph = analyze_tree(input_path) if input_path.is_dir() else analyze_file(input_path)

        written = write_citation_report(graph, output_path)
        log.info(
            "found %d citation(s), %d reference(s) -> %s",
            len(graph.citations),
            len(graph.references),
            written,
        )

        if args.dot:
            dot_path = write_dot_graph(graph, args.dot)
            log.info("DOT graph -> %s", dot_path)

    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
