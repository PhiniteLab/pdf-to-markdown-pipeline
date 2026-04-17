"""Scholarly metadata extraction from converted Markdown files.

Extracts:
  - Title, authors, abstract, keywords
  - DOI, journal, volume/issue, date
  - Funding acknowledgement

Produces YAML front-matter and optional BibTeX/APA citation.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cortexmark.common import load_config, resolve_configured_path, resolve_quality_report_path, setup_logging

# ── Extraction patterns ──────────────────────────────────────────────────────

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;\"')\]]+)")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
KEYWORDS_HEADER_RE = re.compile(r"^\*{0,2}Keywords?\*{0,2}\s*[:.]?\s*", re.IGNORECASE)
ABSTRACT_HEADER_RE = re.compile(r"^\*{0,2}Abstract\*{0,2}\s*[:.]?\s*", re.IGNORECASE)
FUNDING_RE = re.compile(
    r"(?:fund(?:ed|ing)|grant|support(?:ed)?|acknowledg(?:e|ement))\b.{0,200}",
    re.IGNORECASE,
)
VOLUME_ISSUE_RE = re.compile(
    r"(?:vol(?:ume)?\.?\s*(\d+))[,\s]*(?:(?:no|issue|number)\.?\s*(\d+))?",
    re.IGNORECASE,
)
JOURNAL_LINE_RE = re.compile(
    r"(?:journal|proceedings|transactions|letters|review|annals)\s+(?:of\s+)?[\w\s&-]+",
    re.IGNORECASE,
)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class ScholarlyMetadata:
    """Structured metadata extracted from a document."""

    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    keywords: list[str] = field(default_factory=list)
    doi: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    year: str = ""
    emails: list[str] = field(default_factory=list)
    funding: str = ""
    source_file: str = ""


# ── Extraction engine ────────────────────────────────────────────────────────


def extract_title(lines: list[str]) -> str:
    """Extract the document title from the first heading or first non-empty line."""
    for line in lines[:30]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    # Fallback: first substantial non-empty line
    for line in lines[:10]:
        stripped = line.strip()
        if stripped and not stripped.startswith(("---", "```", "|", ">")):
            return stripped
    return ""


def extract_authors(lines: list[str]) -> list[str]:
    """Heuristic: look for author-like lines near the title (lines 1-20).

    Authors are typically comma/and-separated names after the title.
    """
    authors: list[str] = []
    title_seen = False
    for line in lines[:25]:
        stripped = line.strip()
        if stripped.startswith("# "):
            title_seen = True
            continue
        if not title_seen:
            continue
        if not stripped or stripped.startswith(("#", "---", "```", "|", ">")):
            if authors:
                break
            continue
        # Skip lines that look like abstract/keyword headers
        if ABSTRACT_HEADER_RE.match(stripped) or KEYWORDS_HEADER_RE.match(stripped):
            break
        # Author lines tend to have commas or "and"
        if "," in stripped or " and " in stripped.lower():
            # Split by comma and "and"
            parts = re.split(r",\s*|\s+and\s+", stripped, flags=re.IGNORECASE)
            for part in parts:
                name = part.strip().rstrip(".")
                # Filter out non-name tokens (too short, numeric, etc.)
                if len(name) > 2 and not name.isdigit() and not name.startswith("http"):
                    authors.append(name)
            break
    return authors


def extract_abstract(text: str) -> str:
    """Extract abstract section from the document text."""
    lines = text.split("\n")
    collecting = False
    abstract_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if ABSTRACT_HEADER_RE.match(stripped):
            # Start collecting; strip the header prefix
            remainder = ABSTRACT_HEADER_RE.sub("", stripped).strip()
            if remainder:
                abstract_lines.append(remainder)
            collecting = True
            continue
        if collecting:
            # Stop at next heading, keywords, or empty after content
            if stripped.startswith("#") or KEYWORDS_HEADER_RE.match(stripped):
                break
            if not stripped and abstract_lines:
                break
            if stripped:
                abstract_lines.append(stripped)

    return " ".join(abstract_lines).strip()


def extract_keywords(text: str) -> list[str]:
    """Extract keywords from a Keywords: line."""
    for line in text.split("\n"):
        stripped = line.strip()
        if KEYWORDS_HEADER_RE.match(stripped):
            remainder = KEYWORDS_HEADER_RE.sub("", stripped).strip()
            if remainder:
                # Split by comma or semicolon
                parts = re.split(r"[;,]\s*", remainder)
                return [kw.strip().rstrip(".") for kw in parts if kw.strip()]
    return []


def extract_doi(text: str) -> str:
    """Extract the first DOI from the text."""
    m = DOI_RE.search(text)
    return m.group(1).rstrip(".") if m else ""


def extract_year(text: str) -> str:
    """Extract the most likely publication year from the first 50 lines."""
    lines_text = "\n".join(text.split("\n")[:50])
    years = YEAR_RE.findall(lines_text)
    if not years:
        return ""
    # Prefer 4-digit years in a reasonable range
    valid = [y for y in years if 1950 <= int(y) <= 2030]
    return valid[0] if valid else ""


def extract_emails(text: str) -> list[str]:
    """Extract email addresses from the document."""
    return list(dict.fromkeys(EMAIL_RE.findall(text[:3000])))


def extract_journal(text: str) -> str:
    """Heuristic: find journal name from first 30 lines."""
    lines_text = "\n".join(text.split("\n")[:30])
    m = JOURNAL_LINE_RE.search(lines_text)
    return m.group(0).strip() if m else ""


def extract_volume_issue(text: str) -> tuple[str, str]:
    """Extract volume and issue numbers."""
    lines_text = "\n".join(text.split("\n")[:30])
    m = VOLUME_ISSUE_RE.search(lines_text)
    if m:
        return m.group(1) or "", m.group(2) or ""
    return "", ""


def extract_funding(text: str) -> str:
    """Extract funding/acknowledgement snippet."""
    m = FUNDING_RE.search(text)
    if m:
        return m.group(0).strip()[:300]
    return ""


def extract_metadata(text: str, source_file: str = "") -> ScholarlyMetadata:
    """Run all extractors on a document and return structured metadata."""
    lines = text.split("\n")
    volume, issue = extract_volume_issue(text)

    return ScholarlyMetadata(
        title=extract_title(lines),
        authors=extract_authors(lines),
        abstract=extract_abstract(text),
        keywords=extract_keywords(text),
        doi=extract_doi(text),
        journal=extract_journal(text),
        volume=volume,
        issue=issue,
        year=extract_year(text),
        emails=extract_emails(text),
        funding=extract_funding(text),
        source_file=source_file,
    )


# ── Output formatters ────────────────────────────────────────────────────────


def to_yaml_frontmatter(meta: ScholarlyMetadata) -> str:
    """Render metadata as YAML front-matter block."""
    parts = ["---"]
    if meta.title:
        parts.append(f'title: "{meta.title}"')
    if meta.authors:
        parts.append("authors:")
        for a in meta.authors:
            parts.append(f'  - "{a}"')
    if meta.doi:
        parts.append(f'doi: "{meta.doi}"')
    if meta.journal:
        parts.append(f'journal: "{meta.journal}"')
    if meta.volume:
        parts.append(f'volume: "{meta.volume}"')
    if meta.issue:
        parts.append(f'issue: "{meta.issue}"')
    if meta.year:
        parts.append(f'year: "{meta.year}"')
    if meta.keywords:
        parts.append("keywords:")
        for kw in meta.keywords:
            parts.append(f'  - "{kw}"')
    if meta.abstract:
        # Truncate for front-matter
        abstract_short = meta.abstract[:500]
        parts.append(f'abstract: "{abstract_short}"')
    if meta.funding:
        parts.append(f'funding: "{meta.funding}"')
    parts.append("---")
    return "\n".join(parts) + "\n"


def to_bibtex(meta: ScholarlyMetadata) -> str:
    """Render metadata as a BibTeX entry."""
    # Generate a cite key from first author surname + year
    cite_key = "unknown"
    if meta.authors:
        surname = meta.authors[0].split()[-1].lower() if meta.authors[0] else "unknown"
        cite_key = f"{surname}{meta.year}" if meta.year else surname
    lines = [f"@article{{{cite_key},"]
    if meta.title:
        lines.append(f"  title = {{{meta.title}}},")
    if meta.authors:
        lines.append(f"  author = {{{' and '.join(meta.authors)}}},")
    if meta.journal:
        lines.append(f"  journal = {{{meta.journal}}},")
    if meta.volume:
        lines.append(f"  volume = {{{meta.volume}}},")
    if meta.issue:
        lines.append(f"  number = {{{meta.issue}}},")
    if meta.year:
        lines.append(f"  year = {{{meta.year}}},")
    if meta.doi:
        lines.append(f"  doi = {{{meta.doi}}},")
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_apa7(meta: ScholarlyMetadata) -> str:
    """Render metadata as an APA 7 citation string."""
    parts: list[str] = []
    # Authors
    if meta.authors:
        author_str = ", ".join(meta.authors)
        parts.append(author_str)
    # Year
    if meta.year:
        parts.append(f"({meta.year}).")
    else:
        parts.append("(n.d.).")
    # Title
    if meta.title:
        parts.append(f"{meta.title}.")
    # Journal (italic)
    if meta.journal:
        journal_part = f"*{meta.journal}*"
        if meta.volume:
            journal_part += f", *{meta.volume}*"
        if meta.issue:
            journal_part += f"({meta.issue})"
        journal_part += "."
        parts.append(journal_part)
    # DOI
    if meta.doi:
        parts.append(f"https://doi.org/{meta.doi}")
    return " ".join(parts)


# ── File/tree operations ─────────────────────────────────────────────────────


def extract_file(file_path: Path) -> ScholarlyMetadata:
    """Extract metadata from a single Markdown file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    return extract_metadata(text, source_file=str(file_path))


def extract_tree(input_root: Path) -> list[ScholarlyMetadata]:
    """Extract metadata from all Markdown files under a directory."""
    md_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not md_files:
        raise FileNotFoundError(f"No markdown files found under: {input_root}")
    return [extract_file(f) for f in md_files]


def write_metadata_report(metadatas: list[ScholarlyMetadata], output_path: Path) -> Path:
    """Write metadata as a JSON report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "documents": len(metadatas),
        "entries": [asdict(m) for m in metadatas],
    }
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract scholarly metadata from converted Markdown files.")
    parser.add_argument("--input", type=Path, help="Markdown file or directory to scan")
    parser.add_argument("--output", type=Path, help="Path for JSON metadata report")
    parser.add_argument(
        "--format",
        choices=["json", "yaml", "bibtex", "apa"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("metadata", cfg)

    input_path = (args.input or resolve_configured_path(cfg, "output_cleaned_md", "outputs/cleaned_md")).resolve()
    output_path = (args.output or resolve_quality_report_path(cfg, "metadata_report.json")).resolve()

    try:
        metadatas = extract_tree(input_path) if input_path.is_dir() else [extract_file(input_path)]

        if args.format == "json":
            written = write_metadata_report(metadatas, output_path)
            log.info("wrote metadata report for %d file(s) → %s", len(metadatas), written)
        elif args.format == "yaml":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            parts = [to_yaml_frontmatter(m) for m in metadatas]
            output_path.write_text("\n".join(parts), encoding="utf-8")
            log.info("wrote YAML front-matter for %d file(s) → %s", len(metadatas), output_path)
        elif args.format == "bibtex":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            parts = [to_bibtex(m) for m in metadatas]
            output_path.write_text("\n".join(parts), encoding="utf-8")
            log.info("wrote BibTeX for %d file(s) → %s", len(metadatas), output_path)
        elif args.format == "apa":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            parts = [to_apa7(m) for m in metadatas]
            output_path.write_text("\n".join(parts), encoding="utf-8")
            log.info("wrote APA 7 for %d file(s) → %s", len(metadatas), output_path)

    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
