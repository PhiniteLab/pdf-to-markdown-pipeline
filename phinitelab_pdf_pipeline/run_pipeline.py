"""Run all pipeline stages in order: convert → clean → chunk → render_templates."""

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
        choices=["convert", "clean", "chunk", "render"],
        default=["convert", "clean", "chunk", "render"],
        help="Which stages to run (default: all)",
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
