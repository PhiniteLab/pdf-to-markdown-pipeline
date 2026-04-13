"""Run all pipeline stages in order: convert → clean → chunk → render_templates."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from phinitelab_pdf_pipeline.common import Manifest, load_config, resolve_path, setup_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the full PhiniteLab PDF Pipeline.")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
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

    manifest = None
    idem_cfg = cfg.get("idempotency", {})
    if idem_cfg.get("enabled", True) and not args.no_manifest:
        manifest = Manifest(resolve_path(idem_cfg.get("manifest_file", "outputs/.manifest.json")))

    engine = args.engine or cfg.get("convert", {}).get("engine", "dual")
    stages = args.stages
    start = time.monotonic()

    try:
        if "convert" in stages:
            from phinitelab_pdf_pipeline.convert import convert_tree

            log.info("── stage: convert [engine=%s] ──", engine)
            input_root = (data_raw / course_id).resolve()
            written = convert_tree(input_root, raw_md.resolve(), engine=engine, cfg=cfg, manifest=manifest)
            log.info("converted %d file(s)", len(written))

        if "clean" in stages:
            from phinitelab_pdf_pipeline.clean import clean_tree

            log.info("── stage: clean ──")
            input_root = (raw_md / course_id).resolve()
            written = clean_tree(input_root, cleaned_md.resolve(), cfg=cfg, manifest=manifest)
            log.info("cleaned %d file(s)", len(written))

        if "chunk" in stages:
            from phinitelab_pdf_pipeline.chunk import DEFAULT_SPLIT_LEVELS, chunk_tree

            log.info("── stage: chunk ──")
            chunk_cfg = cfg.get("chunk", {})
            split_levels = chunk_cfg.get("split_levels", DEFAULT_SPLIT_LEVELS)
            input_root = (cleaned_md / course_id).resolve()
            written = chunk_tree(input_root, chunks_dir.resolve(), manifest=manifest, split_levels=split_levels)
            log.info("wrote %d chunk(s)", len(written))

        if "render" in stages:
            from phinitelab_pdf_pipeline.render_templates import (
                parse_week_entries,
                read_text,
                render_meta_templates,
                render_week_templates,
            )

            log.info("── stage: render_templates ──")
            course_root = (data_raw / course_id).resolve()
            raw_root = (raw_md / course_id).resolve()
            cleaned_root = (cleaned_md / course_id).resolve()
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
