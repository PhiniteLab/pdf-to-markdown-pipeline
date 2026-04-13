"""Cross-reference resolution and linking for scientific Markdown.

Detects and indexes internal cross-references such as:
  - Theorem / Lemma / Definition / Proposition references
  - Equation references: Equation (3), Eq. 5.1
  - Figure / Table references: Figure 2, Table 3.1
  - Section / Chapter references: Section 2.3, Chapter 4
  - Algorithm references: Algorithm 1

Produces a reference index mapping labels → locations and detects
unresolved (dangling) references.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from phinitelab_pdf_pipeline.common import load_config, resolve_path, setup_logging

# ── Reference categories ─────────────────────────────────────────────────────

CATEGORY_THEOREM = "theorem"
CATEGORY_EQUATION = "equation"
CATEGORY_FIGURE = "figure"
CATEGORY_TABLE = "table"
CATEGORY_SECTION = "section"
CATEGORY_ALGORITHM = "algorithm"
CATEGORY_OTHER = "other"

ALL_CATEGORIES: tuple[str, ...] = (
    CATEGORY_THEOREM,
    CATEGORY_EQUATION,
    CATEGORY_FIGURE,
    CATEGORY_TABLE,
    CATEGORY_SECTION,
    CATEGORY_ALGORITHM,
    CATEGORY_OTHER,
)

# ── Detection patterns ───────────────────────────────────────────────────────

# Definition sites: "**Theorem 3.2.**", "**Definition 1 (MDP).**"
DEFINITION_SITE_RE = re.compile(
    r"(?:\*\*)?(?P<kind>Theorem|Lemma|Proposition|Corollary|Definition|"
    r"Assumption|Axiom|Conjecture|Remark|Example|Algorithm)"
    r"\s+(?P<label>[\d]+(?:\.[\d]+)*)"
    r"(?:\s*\((?P<name>[^)]+)\))?"
    r"[.:)]*(?:\*\*)?",
    re.IGNORECASE,
)

# Equation label site: $$...$$  (N) or \tag{N}
EQUATION_LABEL_RE = re.compile(
    r"(?:\$\$.*?\$\$\s*\((?P<label>\d+(?:\.\d+)*)\))"
    r"|(?:\\tag\{(?P<tag>[^}]+)\})",
    re.DOTALL,
)

# Figure definition: ![...](...)  or Figure N:
FIGURE_DEF_RE = re.compile(
    r"(?:Figure|Fig\.)\s+(?P<label>\d+(?:\.\d+)*)\s*[:.]\s*",
    re.IGNORECASE,
)

# Table definition: Table N:
TABLE_DEF_RE = re.compile(
    r"(?:Table|Tbl\.)\s+(?P<label>\d+(?:\.\d+)*)\s*[:.]\s*",
    re.IGNORECASE,
)

# Reference sites (mentions in text)
REF_MENTION_RE = re.compile(
    r"(?P<kind>Theorem|Lemma|Proposition|Corollary|Definition|"
    r"Assumption|Axiom|Remark|Example|Algorithm|"
    r"Equation|Eq\.|Figure|Fig\.|Table|Tbl\.|"
    r"Section|Sec\.|Chapter|Ch\.)"
    r"\s*[\(]?(?P<label>\d+(?:\.\d+)*)[\)]?",
    re.IGNORECASE,
)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class RefDefinition:
    """A defined label location (where a theorem/figure/etc. is declared)."""

    kind: str
    label: str
    name: str = ""
    source_file: str = ""
    line_number: int = 0
    category: str = CATEGORY_OTHER

    @property
    def full_label(self) -> str:
        return f"{self.kind} {self.label}"


@dataclass
class RefMention:
    """A reference mention in text (e.g. 'see Theorem 3.2')."""

    kind: str
    label: str
    source_file: str = ""
    line_number: int = 0
    category: str = CATEGORY_OTHER

    @property
    def full_label(self) -> str:
        return f"{self.kind} {self.label}"


@dataclass
class CrossRefReport:
    """Complete cross-reference analysis for a document or collection."""

    definitions: list[RefDefinition] = field(default_factory=list)
    mentions: list[RefMention] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def resolution_rate(self) -> float:
        total = len(self.resolved) + len(self.unresolved)
        if total == 0:
            return 1.0
        return len(self.resolved) / total


# ── Classification ───────────────────────────────────────────────────────────

_KIND_TO_CATEGORY: dict[str, str] = {}
for _k in (
    "theorem",
    "lemma",
    "proposition",
    "corollary",
    "definition",
    "assumption",
    "axiom",
    "conjecture",
    "remark",
    "example",
):
    _KIND_TO_CATEGORY[_k] = CATEGORY_THEOREM
for _k in ("equation", "eq."):
    _KIND_TO_CATEGORY[_k] = CATEGORY_EQUATION
for _k in ("figure", "fig."):
    _KIND_TO_CATEGORY[_k] = CATEGORY_FIGURE
for _k in ("table", "tbl."):
    _KIND_TO_CATEGORY[_k] = CATEGORY_TABLE
for _k in ("section", "sec.", "chapter", "ch."):
    _KIND_TO_CATEGORY[_k] = CATEGORY_SECTION
_KIND_TO_CATEGORY["algorithm"] = CATEGORY_ALGORITHM


def classify_kind(kind: str) -> str:
    """Map a reference kind string to a category."""
    return _KIND_TO_CATEGORY.get(kind.lower(), CATEGORY_OTHER)


# ── Extraction ───────────────────────────────────────────────────────────────


def extract_definitions(text: str, source_file: str = "") -> list[RefDefinition]:
    """Extract all label definition sites from text."""
    defs: list[RefDefinition] = []
    lines = text.splitlines()

    for line_num, line in enumerate(lines, start=1):
        for m in DEFINITION_SITE_RE.finditer(line):
            kind = m.group("kind")
            label = m.group("label")
            name = m.group("name") or ""
            defs.append(
                RefDefinition(
                    kind=kind.capitalize(),
                    label=label,
                    name=name,
                    source_file=source_file,
                    line_number=line_num,
                    category=classify_kind(kind),
                )
            )

        for m in FIGURE_DEF_RE.finditer(line):
            label = m.group("label")
            defs.append(
                RefDefinition(
                    kind="Figure",
                    label=label,
                    source_file=source_file,
                    line_number=line_num,
                    category=CATEGORY_FIGURE,
                )
            )

        for m in TABLE_DEF_RE.finditer(line):
            label = m.group("label")
            defs.append(
                RefDefinition(
                    kind="Table",
                    label=label,
                    source_file=source_file,
                    line_number=line_num,
                    category=CATEGORY_TABLE,
                )
            )

    # Equation labels (may span multiple lines)
    for m in EQUATION_LABEL_RE.finditer(text):
        label = m.group("label") or m.group("tag")
        if label:
            offset = text[: m.start()].count("\n") + 1
            defs.append(
                RefDefinition(
                    kind="Equation",
                    label=label,
                    source_file=source_file,
                    line_number=offset,
                    category=CATEGORY_EQUATION,
                )
            )

    return defs


def extract_mentions(text: str, source_file: str = "") -> list[RefMention]:
    """Extract all reference mentions from text."""
    mentions: list[RefMention] = []
    lines = text.splitlines()

    for line_num, line in enumerate(lines, start=1):
        for m in REF_MENTION_RE.finditer(line):
            kind = m.group("kind")
            label = m.group("label")
            mentions.append(
                RefMention(
                    kind=_normalize_kind(kind),
                    label=label,
                    source_file=source_file,
                    line_number=line_num,
                    category=classify_kind(kind),
                )
            )

    return mentions


def _normalize_kind(kind: str) -> str:
    """Normalize abbreviated kinds to canonical form."""
    mapping = {
        "eq.": "Equation",
        "fig.": "Figure",
        "tbl.": "Table",
        "sec.": "Section",
        "ch.": "Chapter",
    }
    return mapping.get(kind.lower(), kind.capitalize())


def resolve_references(
    definitions: list[RefDefinition],
    mentions: list[RefMention],
) -> CrossRefReport:
    """Match mentions against definitions, identify resolved/unresolved."""
    def_index: set[str] = set()
    for d in definitions:
        norm_kind = _normalize_kind(d.kind)
        def_index.add(f"{norm_kind} {d.label}".lower())

    resolved: list[str] = []
    unresolved: list[str] = []
    seen: set[str] = set()

    for mention in mentions:
        norm_kind = _normalize_kind(mention.kind)
        key = f"{norm_kind} {mention.label}".lower()
        if key in seen:
            continue
        seen.add(key)
        if key in def_index:
            resolved.append(mention.full_label)
        else:
            unresolved.append(mention.full_label)

    return CrossRefReport(
        definitions=definitions,
        mentions=mentions,
        resolved=resolved,
        unresolved=unresolved,
    )


# ── File / tree operations ───────────────────────────────────────────────────


def analyze_file(file_path: Path) -> CrossRefReport:
    """Analyze cross-references in a single Markdown file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")
    defs = extract_definitions(text, source_file=str(file_path))
    mentions = extract_mentions(text, source_file=str(file_path))
    return resolve_references(defs, mentions)


def analyze_tree(input_root: Path) -> CrossRefReport:
    """Analyze cross-references across all Markdown files in a directory."""
    md_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not md_files:
        raise FileNotFoundError(f"No markdown files found under: {input_root}")

    all_defs: list[RefDefinition] = []
    all_mentions: list[RefMention] = []

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        all_defs.extend(extract_definitions(text, source_file=str(md_path)))
        all_mentions.extend(extract_mentions(text, source_file=str(md_path)))

    return resolve_references(all_defs, all_mentions)


# ── Output ───────────────────────────────────────────────────────────────────


def write_report(report: CrossRefReport, output_path: Path) -> Path:
    """Write cross-reference analysis as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    category_counts: dict[str, int] = {}
    for m in report.mentions:
        category_counts[m.category] = category_counts.get(m.category, 0) + 1

    data: dict[str, Any] = {
        "summary": {
            "total_definitions": len(report.definitions),
            "total_mentions": len(report.mentions),
            "resolved": len(report.resolved),
            "unresolved": len(report.unresolved),
            "resolution_rate": round(report.resolution_rate, 3),
            "category_counts": category_counts,
        },
        "definitions": [asdict(d) for d in report.definitions],
        "mentions": [asdict(m) for m in report.mentions],
        "resolved": report.resolved,
        "unresolved": report.unresolved,
    }
    output_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect and resolve internal cross-references in Markdown.")
    parser.add_argument("--input", type=Path, help="Markdown file or directory")
    parser.add_argument("--output", type=Path, help="Path for cross-ref report (JSON)")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("cross_ref", cfg)

    input_path = (args.input or resolve_path(cfg["paths"]["output_raw_md"])).resolve()
    output_path = (args.output or resolve_path("outputs/quality/cross_refs.json")).resolve()

    try:
        report = analyze_tree(input_path) if input_path.is_dir() else analyze_file(input_path)
        written = write_report(report, output_path)
        log.info(
            "found %d def(s), %d mention(s), %d unresolved → %s",
            len(report.definitions),
            len(report.mentions),
            len(report.unresolved),
            written,
        )
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
