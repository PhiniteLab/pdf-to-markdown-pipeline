"""Multi-format output: convert cleaned Markdown to HTML, plain text, or YAML.

Supported formats:
  - html:  Markdown → standalone HTML page with optional CSS
  - text:  Markdown → stripped plain-text (no markup)
  - yaml:  Markdown → structured YAML with front-matter + body

Operates on single files or directory trees.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from typing import Any

import yaml

from phinitelab_pdf_pipeline.common import load_config, resolve_path, setup_logging

# ── Markdown → HTML (lightweight, no external dependency) ────────────────────

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
TABLE_ROW_RE = re.compile(r"^\|(.+)\|$")
TABLE_SEP_RE = re.compile(r"^\|\s*[-:]+[-|\s:]*\|$")

DEFAULT_CSS = """
body { font-family: system-ui, -apple-system, sans-serif; max-width: 52rem;
       margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #1a1a1a; }
h1, h2, h3 { margin-top: 1.5em; }
pre { background: #f4f4f4; padding: 1rem; overflow-x: auto; border-radius: 4px; }
code { background: #f4f4f4; padding: 0.15em 0.3em; border-radius: 3px; font-size: 0.9em; }
pre code { background: none; padding: 0; }
blockquote { border-left: 3px solid #ccc; margin: 1em 0; padding: 0.5em 1em; color: #555; }
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #ddd; padding: 0.5em 0.8em; text-align: left; }
th { background: #f4f4f4; }
img { max-width: 100%; }
"""


def _inline_html(text: str) -> str:
    """Convert inline Markdown to HTML."""
    text = html.escape(text)
    text = IMG_RE.sub(r'<img src="\2" alt="\1">', text)
    text = LINK_RE.sub(r'<a href="\2">\1</a>', text)
    text = BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = ITALIC_RE.sub(r"<em>\1</em>", text)
    text = CODE_SPAN_RE.sub(r"<code>\1</code>", text)
    return text


def md_to_html(text: str, *, title: str = "", css: str = DEFAULT_CSS) -> str:
    """Convert Markdown text to a standalone HTML page."""
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    in_list = False
    in_table = False
    table_header_done = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code blocks
        if stripped.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                lang = stripped[3:].strip()
                cls = f' class="language-{html.escape(lang)}"' if lang else ""
                out.append(f"<pre><code{cls}>")
                in_code = True
            i += 1
            continue
        if in_code:
            out.append(html.escape(line))
            i += 1
            continue

        # Tables
        if TABLE_ROW_RE.match(stripped):
            if not in_table:
                out.append("<table>")
                in_table = True
                table_header_done = False
            if TABLE_SEP_RE.match(stripped):
                table_header_done = True
                i += 1
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            tag = "th" if not table_header_done else "td"
            row = "".join(f"<{tag}>{_inline_html(c)}</{tag}>" for c in cells)
            out.append(f"<tr>{row}</tr>")
            i += 1
            continue
        if in_table:
            out.append("</table>")
            in_table = False
            table_header_done = False

        # Headings
        hm = HEADING_RE.match(stripped)
        if hm:
            level = len(hm.group(1))
            content = _inline_html(hm.group(2))
            out.append(f"<h{level}>{content}</h{level}>")
            i += 1
            continue

        # Unordered lists
        if stripped.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_html(stripped[2:])}</li>")
            i += 1
            continue
        if in_list:
            out.append("</ul>")
            in_list = False

        # Ordered lists
        ol_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if ol_match:
            if not in_list:
                out.append("<ol>")
                in_list = True
            out.append(f"<li>{_inline_html(ol_match.group(2))}</li>")
            i += 1
            continue
        if in_list and not ol_match:
            if out and "<ol>" in "\n".join(out[-5:]):
                out.append("</ol>")
            in_list = False

        # Blockquotes
        if stripped.startswith("> "):
            out.append(f"<blockquote>{_inline_html(stripped[2:])}</blockquote>")
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            out.append("<hr>")
            i += 1
            continue

        # Empty line
        if not stripped:
            i += 1
            continue

        # Paragraph
        out.append(f"<p>{_inline_html(stripped)}</p>")
        i += 1

    # Close any open tags
    if in_code:
        out.append("</code></pre>")
    if in_list:
        out.append("</ul>")
    if in_table:
        out.append("</table>")

    page_title = html.escape(title) if title else "Document"
    body = "\n".join(out)
    return (
        f'<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        f'<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{page_title}</title>\n<style>{css}</style>\n</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


# ── Markdown → Plain text ────────────────────────────────────────────────────

STRIP_HEADING_RE = re.compile(r"^#{1,6}\s+")
STRIP_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
STRIP_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
STRIP_CODE_RE = re.compile(r"`([^`]+)`")
STRIP_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
STRIP_IMG_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")


def md_to_text(text: str) -> str:
    """Strip Markdown formatting to produce plain text."""
    lines: list[str] = []
    in_code = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            lines.append(line)
            continue
        # Strip table separators
        if TABLE_SEP_RE.match(stripped):
            continue
        # Strip table pipes
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            lines.append("  ".join(cells))
            continue
        # Strip markdown syntax
        result = STRIP_HEADING_RE.sub("", stripped)
        result = STRIP_IMG_RE.sub(r"\1", result)
        result = STRIP_LINK_RE.sub(r"\1", result)
        result = STRIP_BOLD_RE.sub(r"\1", result)
        result = STRIP_ITALIC_RE.sub(r"\1", result)
        result = STRIP_CODE_RE.sub(r"\1", result)
        result = re.sub(r"^>\s*", "", result)
        result = re.sub(r"^[-*]\s+", "- ", result)
        lines.append(result)
    return "\n".join(lines).strip() + "\n"


# ── Markdown → YAML ──────────────────────────────────────────────────────────


def md_to_yaml(text: str, *, source: str = "") -> str:
    """Convert Markdown to structured YAML document."""
    lines = text.split("\n")
    title = ""
    headings: list[str] = []
    body_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        hm = HEADING_RE.match(stripped)
        if hm:
            if not title and len(hm.group(1)) == 1:
                title = hm.group(2).strip()
            headings.append(hm.group(2).strip())
        elif stripped:
            body_lines.append(stripped)

    data: dict[str, Any] = {
        "title": title or "Untitled",
        "source": source,
        "headings": headings,
        "body": "\n".join(body_lines),
    }
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ── File / tree operations ───────────────────────────────────────────────────

FORMAT_EXTENSIONS = {
    "html": ".html",
    "text": ".txt",
    "yaml": ".yaml",
}


def convert_file(
    input_path: Path,
    output_dir: Path,
    *,
    fmt: str = "html",
    css: str = DEFAULT_CSS,
) -> Path:
    """Convert a single Markdown file to the target format."""
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    text = input_path.read_text(encoding="utf-8")
    ext = FORMAT_EXTENSIONS.get(fmt, ".html")
    output_path = output_dir / (input_path.stem + ext)
    output_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "html":
        result = md_to_html(text, title=input_path.stem, css=css)
    elif fmt == "text":
        result = md_to_text(text)
    elif fmt == "yaml":
        result = md_to_yaml(text, source=str(input_path))
    else:
        raise ValueError(f"Unsupported format: {fmt}")

    output_path.write_text(result, encoding="utf-8")
    return output_path


def convert_tree(
    input_root: Path,
    output_root: Path,
    *,
    fmt: str = "html",
    css: str = DEFAULT_CSS,
) -> list[Path]:
    """Convert all Markdown files in a directory tree."""
    md_files = sorted(p for p in input_root.rglob("*.md") if p.is_file())
    if not md_files:
        raise FileNotFoundError(f"No markdown files found under: {input_root}")

    written: list[Path] = []
    for md_path in md_files:
        relative = md_path.relative_to(input_root)
        target_dir = output_root / relative.parent
        written.append(convert_file(md_path, target_dir, fmt=fmt, css=css))
    return written


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert Markdown files to HTML, plain text, or YAML.")
    parser.add_argument("--input", type=Path, help="Markdown file or directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory")
    parser.add_argument(
        "--format",
        choices=["html", "text", "yaml"],
        default="html",
        help="Target format (default: html)",
    )
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("multi_format", cfg)

    input_path = (args.input or resolve_path(cfg["paths"]["output_cleaned_md"])).resolve()
    output_dir = (args.output_dir or resolve_path(f"outputs/{args.format}")).resolve()

    try:
        if input_path.is_dir():
            written = convert_tree(input_path, output_dir, fmt=args.format)
        else:
            written = [convert_file(input_path, output_dir, fmt=args.format)]

        log.info(
            "converted %d file(s) to %s → %s",
            len(written),
            args.format,
            output_dir,
        )

    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
