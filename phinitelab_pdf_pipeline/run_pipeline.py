"""Run all pipeline stages in order: convert → clean → chunk → render → analyze → validate."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from phinitelab_pdf_pipeline.common import Manifest, load_config, resolve_path, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full PhiniteLab PDF Pipeline.")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    parser.add_argument("--input", type=Path, help="Input directory or PDF file (overrides config course_id)")
    parser.add_argument("--session-name", type=str, help="Session name used to scope output sub-directories")
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=["convert", "clean", "chunk", "render", "analyze", "validate"],
        default=["convert", "clean", "chunk", "render"],
        help="Which stages to run (default: convert clean chunk render). "
        "Use 'analyze' for semantic-chunk / cross-ref / algorithm / notation analysis, "
        "and 'validate' for formula validation / scientific QA / citation context.",
    )
    parser.add_argument("--engine", choices=["docling", "markitdown", "dual"], help="Conversion engine override")
    parser.add_argument("--no-manifest", action="store_true", help="Disable idempotency manifest")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("pipeline", cfg)

    course_id = cfg.get("course_id", "mkt4822-RL")
    data_raw = resolve_path(cfg["paths"]["data_raw"])
    raw_md = resolve_path(cfg["paths"]["output_raw_md"])
    cleaned_md = resolve_path(cfg["paths"]["output_cleaned_md"])
    chunks_dir = resolve_path(cfg["paths"]["output_chunks"])

    # --session-name scopes output directories under session sub-folder
    if args.session_name:
        raw_md = raw_md / args.session_name
        cleaned_md = cleaned_md / args.session_name
        chunks_dir = chunks_dir / args.session_name

    # --input overrides the default data_raw/course_id path
    if args.input:
        custom_input = Path(args.input).resolve()
        convert_input_root = custom_input.parent if custom_input.is_file() else custom_input
        # Derive a relative label from input path for output sub-directories
        try:
            rel_label = str(custom_input.relative_to(data_raw.resolve()))
            if custom_input.is_file():
                rel_label = str(custom_input.parent.relative_to(data_raw.resolve()))
        except ValueError:
            rel_label = custom_input.stem if custom_input.is_file() else custom_input.name
    else:
        convert_input_root = (data_raw / course_id).resolve()
        rel_label = course_id

    manifest = None
    idem_cfg = cfg.get("idempotency", {})
    if idem_cfg.get("enabled", True) and not args.no_manifest:
        manifest_base = resolve_path(idem_cfg.get("manifest_file", "outputs/.manifest.json"))
        if args.session_name:
            manifest_path = manifest_base.parent / f".manifest-{args.session_name}.json"
        else:
            manifest_path = manifest_base
        manifest = Manifest(manifest_path)

    engine = args.engine or cfg.get("convert", {}).get("engine", "dual")
    stages = args.stages
    start = time.monotonic()

    try:
        if "convert" in stages:
            from phinitelab_pdf_pipeline.convert import convert_tree

            log.info("── stage: convert [engine=%s] ──", engine)
            written = convert_tree(convert_input_root, raw_md.resolve(), engine=engine, cfg=cfg, manifest=manifest)
            log.info("converted %d file(s)", len(written))

        if "clean" in stages:
            from phinitelab_pdf_pipeline.clean import clean_tree

            log.info("── stage: clean ──")
            input_root = (raw_md / rel_label).resolve()
            written = clean_tree(input_root, cleaned_md.resolve(), cfg=cfg, manifest=manifest)
            log.info("cleaned %d file(s)", len(written))

        if "chunk" in stages:
            from phinitelab_pdf_pipeline.chunk import DEFAULT_SPLIT_LEVELS, chunk_tree

            log.info("── stage: chunk ──")
            chunk_cfg = cfg.get("chunk", {})
            split_levels = chunk_cfg.get("split_levels", DEFAULT_SPLIT_LEVELS)
            input_root = (cleaned_md / rel_label).resolve()
            written = chunk_tree(input_root, chunks_dir.resolve(), manifest=manifest, split_levels=split_levels)
            log.info("wrote %d chunk(s)", len(written))

        if "render" in stages:
            if args.input:
                log.info("── stage: render_templates ── skipped (custom --input)")
            else:
                from phinitelab_pdf_pipeline.render_templates import (
                    parse_week_entries,
                    read_text,
                    render_meta_templates,
                    render_week_templates,
                )

                log.info("── stage: render_templates ──")
                course_root = (data_raw / rel_label).resolve()
                raw_root = (raw_md / rel_label).resolve()
                cleaned_root = (cleaned_md / rel_label).resolve()
                syllabus_path = raw_root / "00_meta" / "MKT4822_syllabus.md"
                syllabus_text = read_text(syllabus_path)
                week_entries = parse_week_entries(syllabus_text)
                written_list: list[Path] = []
                written_list.extend(render_meta_templates(course_root, syllabus_text, week_entries))
                written_list.extend(render_week_templates(course_root, raw_root, cleaned_root, week_entries, cfg=cfg))
                log.info("populated %d template(s)", len(written_list))

        if "analyze" in stages:
            analysis_input = (cleaned_md / rel_label).resolve()
            quality_dir = resolve_path("outputs/quality")

            from phinitelab_pdf_pipeline.semantic_chunk import chunk_tree as semantic_chunk_tree

            log.info("── stage: analyze / semantic-chunk ──")
            sem_out = resolve_path("outputs/semantic_chunks")
            if args.session_name:
                sem_out = sem_out / args.session_name
            sem_written = semantic_chunk_tree(analysis_input, sem_out.resolve(), manifest=manifest)
            log.info("wrote %d semantic chunk(s)", len(sem_written))

            from phinitelab_pdf_pipeline.cross_ref import analyze_tree as crossref_tree
            from phinitelab_pdf_pipeline.cross_ref import write_report as crossref_write

            log.info("── stage: analyze / cross-ref ──")
            cr_report = crossref_tree(analysis_input)
            crossref_write(cr_report, quality_dir / "crossref_report.json")
            log.info(
                "cross-ref: %d definitions, %.0f%% resolved",
                len(cr_report.definitions),
                cr_report.resolution_rate * 100,
            )

            from phinitelab_pdf_pipeline.algorithm_extract import build_summary as algo_summary
            from phinitelab_pdf_pipeline.algorithm_extract import extract_from_tree as algo_tree
            from phinitelab_pdf_pipeline.algorithm_extract import write_report as algo_write

            log.info("── stage: analyze / algorithm-extract ──")
            al_algos = algo_tree(analysis_input)
            al_summ = algo_summary(al_algos)
            algo_write(al_algos, quality_dir / "algorithm_report.json")
            log.info(
                "algorithms: %d found",
                al_summ.get("total_algorithms", 0),
            )

            from phinitelab_pdf_pipeline.notation_glossary import build_summary as notation_summary
            from phinitelab_pdf_pipeline.notation_glossary import extract_from_tree as notation_tree
            from phinitelab_pdf_pipeline.notation_glossary import write_report as notation_write

            log.info("── stage: analyze / notation-glossary ──")
            nt_glossary = notation_tree(analysis_input)
            nt_summ = notation_summary(nt_glossary)
            notation_write(nt_glossary, quality_dir / "notation_report.json")
            log.info(
                "notation: %d unique symbols, %d entries",
                nt_summ.get("unique_symbols", 0),
                nt_summ.get("total_entries", 0),
            )

        if "validate" in stages:
            validate_input = (cleaned_md / rel_label).resolve()
            quality_dir = resolve_path("outputs/quality")

            from phinitelab_pdf_pipeline.formula_validate import build_summary as fv_summary
            from phinitelab_pdf_pipeline.formula_validate import validate_tree as fv_tree
            from phinitelab_pdf_pipeline.formula_validate import write_report as fv_write

            log.info("── stage: validate / formula-validate ──")
            fv_results = fv_tree(validate_input)
            fv_summ = fv_summary(fv_results)
            fv_write(fv_results, fv_summ, quality_dir / "formula_validation.json")
            log.info(
                "formulas: %d total (%d valid, %d errors)",
                fv_summ.total_formulas,
                fv_summ.total_valid,
                fv_summ.total_errors,
            )

            from phinitelab_pdf_pipeline.scientific_qa import analyze_tree as sciqa_tree
            from phinitelab_pdf_pipeline.scientific_qa import build_summary as sciqa_summary
            from phinitelab_pdf_pipeline.scientific_qa import write_report as sciqa_write

            log.info("── stage: validate / scientific-qa ──")
            sq_reports = sciqa_tree(validate_input)
            sq_summ = sciqa_summary(sq_reports)
            sciqa_write(sq_reports, sq_summ, quality_dir / "scientific_qa.json")
            log.info(
                "scientific QA: %d issues (%d errors, %d warnings)",
                sq_summ.total_issues,
                sq_summ.total_errors,
                sq_summ.total_warnings,
            )

            from phinitelab_pdf_pipeline.citation_context import analyze_tree as citctx_tree
            from phinitelab_pdf_pipeline.citation_context import build_summary as citctx_summary
            from phinitelab_pdf_pipeline.citation_context import write_report as citctx_write

            log.info("── stage: validate / citation-context ──")
            cc_reports = citctx_tree(validate_input)
            cc_summ = citctx_summary(cc_reports)
            citctx_write(cc_reports, cc_summ, quality_dir / "citation_context.json")
            log.info(
                "citations: %d total (%d self, %d co-citation pairs)",
                cc_summ.total_citations,
                cc_summ.total_self_citations,
                cc_summ.total_co_citation_pairs,
            )

        if manifest:
            manifest.save()

    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid input: %s", exc)
        return 1

    elapsed = time.monotonic() - start
    log.info("pipeline finished in %.1fs", elapsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
