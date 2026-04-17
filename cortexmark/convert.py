from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cortexmark.common import (
    Manifest,
    detect_device,
    get_source_id,
    load_config,
    mirror_directory_tree,
    resolve_configured_path,
    resolve_manifest_path,
    runtime_env_value,
    setup_logging,
)

if TYPE_CHECKING:
    from docling.document_converter import DocumentConverter

FORMULA_PLACEHOLDER = "<!-- formula-not-decoded -->"
ALGORITHM_HINTS = (
    "Algorithm parameter",
    "Algorithm parameters",
    "Input:",
    "Initialize",
    "Loop for each",
    "Loop forever",
    "Take action",
    "Observe",
    "Choose ",
    "until ",
)


# ── Docling helpers ──────────────────────────────────────────────────────────


def build_converter(cfg: dict[str, Any] | None = None) -> DocumentConverter:
    try:
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError:
        raise ImportError(
            "The 'docling' package is required for the docling/dual conversion engine.\n"
            'Install it with:  pip install "cortexmark[docling]"\n'
            'Or for GPU support: pip install "cortexmark[gpu]"'
        ) from None

    dc = (cfg or {}).get("convert", {}).get("docling", {})

    do_table = dc.get("do_table_structure", False)
    table_mode_name = dc.get("table_structure_mode", "accurate")

    table_kwargs: dict[str, Any] = {}
    if do_table:
        from docling.datamodel.pipeline_options import TableFormerMode, TableStructureOptions

        table_mode = TableFormerMode.ACCURATE if table_mode_name == "accurate" else TableFormerMode.FAST
        table_kwargs["table_structure_options"] = TableStructureOptions(mode=table_mode)

    raw_device = dc.get("device", "auto")
    device = detect_device() if raw_device == "auto" else raw_device

    pipeline_options = PdfPipelineOptions(
        accelerator_options=AcceleratorOptions(
            device=device,
            num_threads=dc.get("num_threads", 1),
        ),
        enable_remote_services=False,
        allow_external_plugins=False,
        do_ocr=dc.get("do_ocr", False),
        do_table_structure=do_table,
        force_backend_text=True,
        generate_page_images=False,
        generate_picture_images=False,
        generate_table_images=False,
        generate_parsed_pages=False,
        **table_kwargs,
    )

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)},
    )


def normalize_markdown(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return normalized + "\n"


def normalize_recovered_text(text: str) -> str:
    normalized = " ".join(text.replace("\n", " ").split())
    normalized = normalized.replace(" . =", " =").replace(" . =", " =")
    normalized = normalized.replace(" ,", ",").replace(" .", ".")
    normalized = re.sub(r"\s+([)\]])", r"\1", normalized)
    normalized = re.sub(r"([([=+\-/*])\s+", r"\1 ", normalized)
    return normalized.strip()


def is_algorithmic_text(text: str) -> bool:
    return any(hint in text for hint in ALGORITHM_HINTS)


def format_algorithm_block(text: str) -> str:
    formatted = text
    split_markers = [
        "Input:",
        "Algorithm parameter",
        "Algorithm parameters",
        "Initialize",
        "Loop for each episode:",
        "Loop for each step of episode:",
        "Loop forever:",
        "Loop for t =",
        "Choose ",
        "Take action",
        "Observe ",
        "If ",
        "Else ",
        "until ",
        "Until ",
    ]
    for marker in split_markers:
        formatted = formatted.replace(marker, f"\n{marker}")
    lines = [line.strip() for line in formatted.splitlines() if line.strip()]
    return "```text\n" + "\n".join(lines) + "\n```"


def format_formula_block(text: str) -> str:
    return "\n".join(
        [
            "> Equation (recovered from PDF):",
            ">",
            f"> {text}",
        ]
    )


def format_incomplete_formula_block() -> str:
    return "> Equation present in PDF, but text recovery was incomplete."


def reformat_algorithm_sections(markdown: str) -> str:
    pattern = re.compile(
        r"(?m)^(##\s+.+?)\s+(Algorithm parameter[s]?:.+)$",
    )

    def replacer(match: re.Match[str]) -> str:
        heading = match.group(1).strip()
        algorithm_text = normalize_recovered_text(match.group(2))
        return f"{heading}\n\n{format_algorithm_block(algorithm_text)}"

    return pattern.sub(replacer, markdown)


def render_formula_item(item: Any) -> str:
    recovered = normalize_recovered_text(item.text or item.orig)
    if not recovered:
        return FORMULA_PLACEHOLDER
    if len(re.findall(r"[\w\dα-ωΑ-Ω]", recovered)) < 3:
        return format_incomplete_formula_block()
    if is_algorithmic_text(recovered):
        return format_algorithm_block(recovered)
    return format_formula_block(recovered)


def recover_formula_placeholders(markdown: str, formula_items: list[Any]) -> str:
    recovered_markdown = markdown
    for item in formula_items:
        replacement = render_formula_item(item)
        recovered_markdown = recovered_markdown.replace(FORMULA_PLACEHOLDER, replacement, 1)
    return recovered_markdown


# ── markitdown helpers ───────────────────────────────────────────────────────


def convert_with_markitdown(input_path: Path) -> str:
    """Return raw markdown text produced by markitdown."""
    from markitdown import MarkItDown

    md = MarkItDown()
    result = md.convert(str(input_path))
    return result.text_content or ""


# ── Merge logic ──────────────────────────────────────────────────────────────


def _paragraph_set(text: str) -> set[str]:
    """Extract normalised paragraph fingerprints for deduplication."""
    paragraphs: set[str] = set()
    for block in re.split(r"\n{2,}", text):
        stripped = block.strip()
        if not stripped or stripped.startswith(("#", ">", "```")):
            continue
        normalised = " ".join(stripped.lower().split())
        if len(normalised) > 40:
            paragraphs.add(normalised[:120])
    return paragraphs


def merge_docling_markitdown(docling_md: str, markitdown_md: str) -> str:
    """Merge docling (structure-rich) and markitdown (text-rich) outputs.

    Keep docling output as the structural backbone.  Identify paragraphs
    present in markitdown but absent from docling and append them.
    """
    docling_fingerprints = _paragraph_set(docling_md)
    extra_paragraphs: list[str] = []

    for block in re.split(r"\n{2,}", markitdown_md):
        stripped = block.strip()
        if not stripped or stripped.startswith(("#", ">", "```")):
            continue
        # Skip markitdown table artifacts (page layout garbage)
        if stripped.startswith("|") and stripped.endswith("|"):
            continue
        normalised = " ".join(stripped.lower().split())
        if len(normalised) <= 40:
            continue
        fingerprint = normalised[:120]
        if fingerprint not in docling_fingerprints:
            extra_paragraphs.append(stripped)
            docling_fingerprints.add(fingerprint)

    if not extra_paragraphs:
        return docling_md

    supplement = "\n\n".join(extra_paragraphs)
    return docling_md.rstrip() + "\n\n<!-- markitdown-supplement -->\n\n" + supplement + "\n"


# ── Single-file conversion ──────────────────────────────────────────────────


def convert_pdf(
    input_path: Path,
    output_path: Path,
    *,
    converter: DocumentConverter | None = None,
    engine: str = "dual",
    cfg: dict[str, Any] | None = None,
) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input PDF not found: {input_path}")
    if input_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {input_path.name}")

    docling_md = ""
    markitdown_md = ""

    if engine in ("docling", "dual"):
        active_converter = converter or build_converter(cfg)
        result = active_converter.convert(str(input_path))
        document = result.document
        docling_md = document.export_to_markdown()
        try:
            from docling_core.types.doc.document import FormulaItem
        except ImportError:
            raise ImportError(
                "The 'docling' package is required for formula recovery.\n"
                'Install it with:  pip install "cortexmark[docling]"'
            ) from None

        undecoded_formulas = [
            item
            for item, _level in document.iterate_items()
            if isinstance(item, FormulaItem) and not item.text and item.orig
        ]
        docling_md = recover_formula_placeholders(docling_md, undecoded_formulas)
        docling_md = reformat_algorithm_sections(docling_md)

    if engine in ("markitdown", "dual"):
        markitdown_md = convert_with_markitdown(input_path)

    if engine == "dual":
        markdown = merge_docling_markitdown(docling_md, markitdown_md)
    elif engine == "markitdown":
        markdown = markitdown_md
    else:
        markdown = docling_md

    markdown = normalize_markdown(markdown)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown)
    return output_path


# ── Tree conversion ─────────────────────────────────────────────────────────


def derive_output_path(input_path: Path, input_root: Path, output_root: Path) -> Path:
    relative = input_path.relative_to(input_root)
    return output_root / input_root.name / relative.with_suffix(".md")


def convert_tree(
    input_root: Path,
    output_root: Path,
    *,
    engine: str = "dual",
    cfg: dict[str, Any] | None = None,
    manifest: Manifest | None = None,
) -> list[Path]:
    pdf_files = sorted(p for p in input_root.rglob("*.pdf") if p.is_file())
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found under: {input_root}")

    mirror_directory_tree(input_root, output_root)
    converter = build_converter(cfg) if engine in ("docling", "dual") else None
    written: list[Path] = []
    for pdf_path in pdf_files:
        if manifest and not manifest.needs_update(pdf_path):
            continue
        output_path = derive_output_path(pdf_path, input_root, output_root)
        written.append(convert_pdf(pdf_path, output_path, converter=converter, engine=engine, cfg=cfg))
        if manifest:
            manifest.record(pdf_path)
    return written


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert PDF files to Markdown (docling + markitdown).")
    parser.add_argument("--input", type=Path, help="Source PDF file or source directory")
    parser.add_argument("--output", type=Path, help="Target Markdown path for single-file conversion")
    parser.add_argument("--output-dir", type=Path, help="Output root directory for directory mode")
    parser.add_argument("--engine", choices=["docling", "markitdown", "dual"], help="Conversion engine override")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    parser.add_argument("--no-manifest", action="store_true", help="Disable idempotency manifest")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("convert", cfg)

    source_id = get_source_id(cfg)
    input_path = (args.input or resolve_configured_path(cfg, "data_raw", "data/raw") / source_id).resolve()
    output_dir = (args.output_dir or resolve_configured_path(cfg, "output_raw_md", "outputs/raw_md")).resolve()
    engine = (
        args.engine
        or runtime_env_value("PIPELINE_ENGINE", "CORTEXMARK_ENGINE", cfg=cfg)
        or cfg.get("convert", {}).get("engine", "dual")
    )

    manifest = None
    idem_cfg = cfg.get("idempotency", {})
    if idem_cfg.get("enabled", True) and not args.no_manifest:
        manifest = Manifest(resolve_manifest_path(cfg))

    try:
        if input_path.is_dir():
            if args.output is not None:
                raise ValueError("--output can only be used when --input points to a single PDF file")
            written = convert_tree(input_path, output_dir, engine=engine, cfg=cfg, manifest=manifest)
            if manifest:
                manifest.save()
            log.info("converted %d pdf file(s) under %s [engine=%s]", len(written), input_path, engine)
            return 0

        if args.output is not None:
            output_path = args.output.resolve()
        else:
            output_path = output_dir / input_path.with_suffix(".md").name

        written_path = convert_pdf(input_path, output_path, engine=engine, cfg=cfg)
        if manifest:
            manifest.record(input_path)
            manifest.save()
        log.info("wrote markdown to %s [engine=%s]", written_path, engine)
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid input: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
