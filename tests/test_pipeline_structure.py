"""Comprehensive tests for the pdf-to-markdown pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.chunk import (
    Chunk,
    build_heading_re,
    chunk_file,
    chunk_tree,
    parse_chunks,
    slugify,
)
from scripts.citations import (
    Citation,
    CitationEdge,
    CitationGraph,
    Reference,
    analyze_file,
    analyze_tree,
    build_citation_graph,
    extract_inline_citations,
    extract_references,
    write_citation_report,
    write_dot_graph,
)
from scripts.clean import (
    clean_markdown,
    clean_tree,
    fix_wrapped_lines,
    normalize_heading_lines,
    normalize_table_blocks,
    normalize_table_cell,
    remove_page_numbers,
    remove_repeated_headers_footers,
)
from scripts.common import (
    Manifest,
    file_hash,
    load_config,
    mirror_directory_tree,
    reset_config_cache,
    setup_logging,
)
from scripts.convert import (
    derive_output_path,
    format_algorithm_block,
    format_formula_block,
    format_incomplete_formula_block,
    is_algorithmic_text,
    merge_docling_markitdown,
    normalize_markdown,
    normalize_recovered_text,
    recover_formula_placeholders,
    reformat_algorithm_sections,
)
from scripts.diff import (
    FileDiff,
    TreeDiff,
    diff_files,
    diff_texts,
    diff_trees,
    write_diff_report,
    write_unified_diff,
)
from scripts.doc_type import (
    ALL_TYPES,
    GENERIC,
    PAPER,
    TEXTBOOK,
    DocTypeResult,
    detect_file,
    detect_paper,
    detect_slides,
    detect_syllabus,
    detect_textbook,
    detect_tree,
    detect_type,
    get_template,
    render_template_scaffold,
    write_detection_report,
)
from scripts.figures import (
    FigureEntry,
    FigureReport,
    build_figure_report,
    extract_figures_from_text,
    extract_from_file,
    extract_from_tree,
    write_figure_manifest,
    write_gallery_page,
)
from scripts.formula_score import (
    FileReport,
    build_file_report,
    score_file,
    score_markdown,
    score_tree,
    validate_formula_text,
    write_report,
)
from scripts.ghpages import (
    PageEntry,
    build_document_page,
    build_index_page,
    build_nav_html,
    collect_pages,
    generate_site,
    write_site_manifest,
)
from scripts.metadata import (
    ScholarlyMetadata,
    extract_abstract,
    extract_authors,
    extract_doi,
    extract_file,
    extract_keywords,
    extract_metadata,
    extract_title,
    extract_tree,
    extract_year,
    to_apa7,
    to_bibtex,
    to_yaml_frontmatter,
    write_metadata_report,
)
from scripts.multi_format import (
    FORMAT_EXTENSIONS,
    convert_file,
    convert_tree,
    md_to_html,
    md_to_text,
    md_to_yaml,
)
from scripts.ocr_quality import (
    OCRFileReport,
    OCRQualityMetrics,
    assess_file,
    assess_quality,
    assess_tree,
    confidence_to_grade,
    count_common_words,
    count_garble_chars,
    count_repeat_artefacts,
    count_short_noise_lines,
    count_symbol_soup,
    write_ocr_report,
)
from scripts.parallel import (
    ParallelConfig,
    TaskResult,
    collect_md_files,
    parallel_map,
    parallel_tree,
)
from scripts.plugin import (
    VALID_HOOKS,
    PluginBase,
    PluginInfo,
    PluginRegistry,
    write_plugin_report,
)
from scripts.qa_pipeline import (
    BADGE_FAIL,
    BADGE_GOLD,
    BADGE_SILVER,
    FileQAReport,
    build_summary,
    check_broken_links,
    check_empty_chunks,
    check_encoding_errors,
    check_missing_text,
    check_orphan_headings,
    check_table_integrity,
    compute_badge,
    compute_overall_badge,
    qa_check_text,
    qa_file,
    qa_tree,
    write_markdown_report,
)
from scripts.qa_pipeline import (
    write_report as write_qa_report,
)
from scripts.rag_export import (
    RAGRecord,
    estimate_tokens,
    export_file,
    export_tree,
    make_chunk_id,
    normalize_text_for_embedding,
    parse_chunk_file,
    write_json_array,
    write_jsonl,
)
from scripts.rag_export import (
    build_summary as rag_build_summary,
)
from scripts.render_templates import (
    build_assignment_text,
    build_course_profile_text,
    build_global_rules_text,
    build_week_rules_text,
    extract_line_value,
    extract_section,
    first_items,
    humanize_topic,
    parse_week_entries,
    summarize_text,
)
from scripts.run_pipeline import build_parser
from scripts.topics import (
    TOPIC_KEYWORDS,
    DocumentTopics,
    TopicScore,
    build_topic_distribution,
    classify_file,
    classify_text,
    classify_tree,
    get_top_topics,
    write_topic_report,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


class DummyFormula:
    def __init__(self, orig: str, text: str = "") -> None:
        self.orig = orig
        self.text = text


@pytest.fixture(autouse=True)
def _fresh_config():
    """Ensure each test gets a fresh config cache."""
    reset_config_cache()
    yield
    reset_config_cache()


# ═══════════════════════════════════════════════════════════════════════════════
# common.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfig:
    def test_load_config_from_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("course_id: test-course\npaths:\n  data_raw: data/raw\n", encoding="utf-8")
        cfg = load_config(cfg_file)
        assert cfg["course_id"] == "test-course"

    def test_load_config_missing_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_config_non_mapping_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_config(cfg_file)


class TestLogging:
    def test_setup_logging_returns_logger(self) -> None:
        log = setup_logging("test-logger")
        assert log.name == "test-logger"
        assert log.handlers


class TestMirrorDirectoryTree:
    def test_mirrors_structure(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        (src / "a" / "b").mkdir(parents=True)
        (src / "c").mkdir(parents=True)
        target = mirror_directory_tree(src, tmp_path / "out")
        assert target == tmp_path / "out" / "src"
        assert (target / "a" / "b").is_dir()
        assert (target / "c").is_dir()


class TestFileHash:
    def test_deterministic_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("hello", encoding="utf-8")
        h1 = file_hash(f)
        h2 = file_hash(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")
        assert file_hash(f1) != file_hash(f2)


class TestManifest:
    def test_needs_update_on_new_file(self, tmp_path: Path) -> None:
        f = tmp_path / "input.pdf"
        f.write_bytes(b"pdf-content")
        m = Manifest(tmp_path / ".manifest.json")
        assert m.needs_update(f)

    def test_no_update_after_record(self, tmp_path: Path) -> None:
        f = tmp_path / "input.pdf"
        f.write_bytes(b"pdf-content")
        m = Manifest(tmp_path / ".manifest.json")
        m.record(f)
        assert not m.needs_update(f)

    def test_needs_update_after_file_change(self, tmp_path: Path) -> None:
        f = tmp_path / "input.pdf"
        f.write_bytes(b"v1")
        m = Manifest(tmp_path / ".manifest.json")
        m.record(f)
        f.write_bytes(b"v2")
        assert m.needs_update(f)

    def test_persist_and_reload(self, tmp_path: Path) -> None:
        f = tmp_path / "input.pdf"
        f.write_bytes(b"content")
        manifest_path = tmp_path / ".manifest.json"
        m1 = Manifest(manifest_path)
        m1.record(f)
        m1.save()
        m2 = Manifest(manifest_path)
        assert not m2.needs_update(f)


# ═══════════════════════════════════════════════════════════════════════════════
# convert.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeMarkdown:
    def test_strips_and_adds_newline(self) -> None:
        assert normalize_markdown("  hello  ") == "hello\n"

    def test_normalizes_line_endings(self) -> None:
        assert normalize_markdown("a\r\nb\rc") == "a\nb\nc\n"


class TestNormalizeRecoveredText:
    def test_collapses_whitespace(self) -> None:
        assert "hello world" in normalize_recovered_text("  hello   world  ")

    def test_fixes_punctuation(self) -> None:
        result = normalize_recovered_text("value . = 5 ,")
        assert " . =" not in result


class TestFormatBlocks:
    def test_algorithm_block_wrapped_in_code_fence(self) -> None:
        result = format_algorithm_block("Initialize Q(s,a)")
        assert result.startswith("```text\n")
        assert result.endswith("\n```")
        assert "Initialize Q(s,a)" in result

    def test_formula_block_uses_blockquote(self) -> None:
        result = format_formula_block("q ∗ (a)")
        assert "> Equation (recovered from PDF):" in result
        assert "> q ∗ (a)" in result


class TestReformatAlgorithmSections:
    def test_splits_heading_and_box(self) -> None:
        md = (
            "## Sarsa (on-policy TD control) for estimating Q ≈ q ∗ "
            "Algorithm parameters: step size α ∈ (0 , 1], small ε > 0 Initialize Q ( s, a )\n"
        )
        reformatted = reformat_algorithm_sections(md)
        assert "## Sarsa (on-policy TD control) for estimating Q ≈ q ∗\n\n```text" in reformatted


class TestRecoverFormulaPlaceholders:
    def test_renders_visible_blocks(self) -> None:
        markdown = "Before\n\n<!-- formula-not-decoded -->\n\nAfter\n\n<!-- formula-not-decoded -->\n"
        formula_items = [
            DummyFormula("q ∗ ( a ) . = E [ R t | A t = a ] ."),
            DummyFormula("Input: the policy π Algorithm parameter: step size α ∈ (0 , 1] Initialize V ( s )"),
        ]
        recovered = recover_formula_placeholders(markdown, formula_items)  # type: ignore[arg-type]
        assert "<!-- formula-not-decoded -->" not in recovered
        assert "Equation (recovered from PDF)" in recovered
        assert "```text" in recovered


class TestMergeDoclingMarkitdown:
    def test_no_supplement_when_identical(self) -> None:
        text = "## Heading\n\nThis is a paragraph that exists in both engines and should not be duplicated.\n"
        assert merge_docling_markitdown(text, text) == text

    def test_adds_supplement_for_new_paragraphs(self) -> None:
        docling = "## Heading\n\nDocling paragraph about reinforcement learning basics.\n"
        markitdown = "Docling paragraph about reinforcement learning basics.\n\nExtra markitdown paragraph that provides additional context and explanation.\n"
        merged = merge_docling_markitdown(docling, markitdown)
        assert "<!-- markitdown-supplement -->" in merged
        assert "Extra markitdown paragraph" in merged

    def test_skips_table_artifacts(self) -> None:
        docling = "## Heading\n\nSome long paragraph about reinforcement learning concepts in detail.\n"
        markitdown = "| broken | table | artifact | data | garbage | more |\n"
        merged = merge_docling_markitdown(docling, markitdown)
        assert "<!-- markitdown-supplement -->" not in merged

    def test_skips_short_fragments(self) -> None:
        docling = "## Heading\n\nA meaningful paragraph about control theory and optimisation.\n"
        markitdown = "Short text\n\nAnother short\n"
        merged = merge_docling_markitdown(docling, markitdown)
        assert "<!-- markitdown-supplement -->" not in merged


# ═══════════════════════════════════════════════════════════════════════════════
# clean.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestRemovePageNumbers:
    def test_removes_standalone_numbers(self) -> None:
        assert remove_page_numbers(["text", "42", "more"]) == ["text", "more"]

    def test_removes_page_prefix(self) -> None:
        assert remove_page_numbers(["Page 7", "text"]) == ["text"]

    def test_preserves_numbers_in_text(self) -> None:
        assert remove_page_numbers(["Chapter 7 stuff"]) == ["Chapter 7 stuff"]


class TestRemoveRepeatedHeadersFooters:
    def test_removes_repeated_short_lines(self) -> None:
        lines = ["footer text"] * 5 + ["real content"]
        result = remove_repeated_headers_footers(lines)
        assert "footer text" not in result
        assert "real content" in result

    def test_preserves_headings(self) -> None:
        lines = ["## Heading"] * 5 + ["body"]
        result = remove_repeated_headers_footers(lines)
        assert all("## Heading" in line for line in result if line.startswith("##"))


class TestNormalizeHeadingLines:
    def test_combined_chapter_section(self) -> None:
        result = normalize_heading_lines("## CHAPTER 2 SECTION 3")
        assert result == ["# 2", "## 3"]

    def test_chapter_only(self) -> None:
        result = normalize_heading_lines("## Chapter 5: Introduction")
        assert result == ["# 5: Introduction"]

    def test_section_only(self) -> None:
        result = normalize_heading_lines("## Section 3")
        assert result == ["## 3"]

    def test_regular_heading_passthrough(self) -> None:
        result = normalize_heading_lines("## Something Normal")
        assert result == ["## Something Normal"]


class TestFixWrappedLines:
    def test_merges_broken_paragraphs(self) -> None:
        lines = ["This is a", "broken paragraph."]
        result = fix_wrapped_lines(lines)
        assert result == ["This is a broken paragraph."]

    def test_preserves_code_blocks(self) -> None:
        lines = ["```", "code here", "```"]
        result = fix_wrapped_lines(lines)
        assert "code here" in result

    def test_preserves_blockquotes(self) -> None:
        lines = ["", "> quote line"]
        result = fix_wrapped_lines(lines)
        assert "> quote line" in result

    def test_dehyphenates(self) -> None:
        lines = ["reinforce-", "ment learning"]
        result = fix_wrapped_lines(lines)
        assert result == ["reinforcement learning"]


class TestCleanMarkdown:
    def test_normalizes_combined_headings(self) -> None:
        raw = "## CHAPTER 2 SECTION 3\nHello world.\n"
        cleaned = clean_markdown(raw)
        assert cleaned.startswith("# 2\n\n## 3\n\nHello world.\n")

    def test_preserves_equation_and_algorithm_blocks(self) -> None:
        raw = (
            "## Tabular TD(0)\n\n"
            "> Equation (recovered from PDF):\n"
            ">\n"
            "> q ∗ ( a ) = E [ R t | A t = a ]\n\n"
            "```text\n"
            "Algorithm parameter: step size α ∈ (0, 1]\n"
            "Initialize Q(s, a)\n"
            "```\n"
        )
        cleaned = clean_markdown(raw)
        assert "## Tabular TD(0)" in cleaned
        assert "> Equation (recovered from PDF):" in cleaned
        assert "```text" in cleaned

    def test_empty_input(self) -> None:
        assert clean_markdown("") == "\n"

    def test_only_heading(self) -> None:
        result = clean_markdown("## Chapter 1: Test\n")
        assert result.strip().startswith("# 1: Test")

    def test_utf8_preserved(self) -> None:
        result = clean_markdown("α β γ δ ε ζ η θ ι κ λ μ\n")
        assert "α" in result
        assert "μ" in result


class TestCleanTree:
    def test_mirrors_and_cleans(self, tmp_path: Path) -> None:
        input_root = tmp_path / "raw_md" / "mkt4822-RL"
        (input_root / "01_week" / "assignment").mkdir(parents=True)
        (input_root / "02_intro_rl").mkdir(parents=True)
        (input_root / "02_intro_rl" / "content.md").write_text("## CHAPTER 1 SECTION 1\nSample\n", encoding="utf-8")
        output_root = tmp_path / "cleaned_md"
        written = clean_tree(input_root, output_root)
        assert len(written) == 1
        assert (output_root / "mkt4822-RL" / "01_week" / "assignment").is_dir()
        assert (output_root / "mkt4822-RL" / "02_intro_rl" / "content.md").is_file()


# ═══════════════════════════════════════════════════════════════════════════════
# chunk.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Hello World!") == "hello-world"

    def test_empty(self) -> None:
        assert slugify("!!!") == "untitled"


class TestParseChunks:
    def test_basic(self) -> None:
        chunks = parse_chunks("# Intro\n\nAlpha\n\n## Part A\n\nBeta\n")
        assert [c.title for c in chunks] == ["Intro", "Part A"]

    def test_empty_input(self) -> None:
        assert parse_chunks("") == []

    def test_only_headings(self) -> None:
        chunks = parse_chunks("# A\n\n## B\n")
        assert chunks == []  # no body content

    def test_body_without_heading(self) -> None:
        chunks = parse_chunks("Some text without any heading.\n")
        assert len(chunks) == 1
        assert chunks[0].title == "untitled"


class TestChunkRender:
    def test_render_with_both_headings(self) -> None:
        c = Chunk(chapter="Ch1", section="Sec1", body=["text"])
        rendered = c.render()
        assert "# Ch1" in rendered
        assert "## Sec1" in rendered
        assert "text" in rendered


class TestChunkTree:
    def test_mirrors_and_chunks(self, tmp_path: Path) -> None:
        input_root = tmp_path / "cleaned_md" / "mkt4822-RL"
        (input_root / "05_coding" / "assignment").mkdir(parents=True)
        (input_root / "02_intro_rl").mkdir(parents=True)
        (input_root / "02_intro_rl" / "content.md").write_text("# Intro\n\n## Basics\n\nBody text.\n", encoding="utf-8")
        output_root = tmp_path / "chunks"
        written = chunk_tree(input_root, output_root)
        assert len(written) == 1
        assert (output_root / "mkt4822-RL" / "05_coding" / "assignment").is_dir()
        assert written[0].name.startswith("chunk_001_")

    def test_chunk_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            chunk_file(tmp_path / "nonexistent.md", tmp_path / "out")

    def test_chunk_file_no_chunks(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="No logical chunks"):
            chunk_file(f, tmp_path / "out")


# ═══════════════════════════════════════════════════════════════════════════════
# render_templates.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseWeekEntries:
    def test_deterministic(self) -> None:
        syllabus = (
            "## Week 2: Introduction to Reinforcement Learning\n"
            "- RL as interaction\n"
            "- Delayed reward\n"
            "## Week 3: Multi-Armed Bandits\n"
            "- Exploration vs exploitation\n"
        )
        entries = parse_week_entries(syllabus)
        assert entries[2]["title"] == "Introduction to Reinforcement Learning"
        assert entries[2]["bullets"] == ["RL as interaction", "Delayed reward"]
        assert entries[3]["title"] == "Multi-Armed Bandits"

    def test_empty_input(self) -> None:
        assert parse_week_entries("") == {}

    def test_no_weeks(self) -> None:
        assert parse_week_entries("## Some Other Heading\ncontent\n") == {}


class TestExtractHelpers:
    def test_extract_line_value(self) -> None:
        text = "Course Title: Reinforcement Learning\nInstructor: Dr. X\n"
        assert extract_line_value(text, "Course Title", "?") == "Reinforcement Learning"
        assert extract_line_value(text, "Missing", "default") == "default"

    def test_extract_section(self) -> None:
        text = "## Required Programs\n- Python\n- Matlab\n## Next\nstuff\n"
        section = extract_section(text, "Required Programs")
        assert "Python" in section
        assert "Matlab" in section

    def test_extract_section_missing(self) -> None:
        assert extract_section("## Other\ndata\n", "Missing") == ""


class TestHumanizeTopic:
    def test_strips_number_prefix(self) -> None:
        assert humanize_topic("03_bandits") == "Bandits"

    def test_acronyms(self) -> None:
        assert humanize_topic("09_td") == "TD"
        assert humanize_topic("04_mdp") == "MDP"


class TestFirstItems:
    def test_deduplicates(self) -> None:
        assert first_items(["a", "b", "a", "c"], 3) == ["a", "b", "c"]

    def test_limit(self) -> None:
        assert first_items(["x", "y", "z"], 2) == ["x", "y"]


class TestSummarizeText:
    def test_short_passthrough(self) -> None:
        assert summarize_text("Short.", max_chars=100) == "Short."

    def test_truncates_long(self) -> None:
        long = "A" * 300
        result = summarize_text(long, max_chars=50)
        assert len(result) <= 50
        assert result.endswith("…")


class TestBuildTemplates:
    def test_course_profile(self) -> None:
        text = build_course_profile_text(
            course_title="RL",
            semester="Fall",
            instructor="Dr. X",
            main_topics=["RL", "MDP"],
            programs=["Python"],
            notes=["Note 1"],
        )
        assert "# Course Profile" in text
        assert "- RL" in text
        assert "- Python" in text

    def test_global_rules(self) -> None:
        text = build_global_rules_text(["R1"], ["R2"], ["R3"])
        assert "# Global Rules" in text
        assert "- R1" in text
        assert "- R2" in text

    def test_week_rules(self) -> None:
        text = build_week_rules_text(3, "Bandits", ["S1"], ["E1"], ["O1"])
        assert "# Week 03 Rules" in text
        assert "## Scope" in text

    def test_assignment(self) -> None:
        text = build_assignment_text(5, "Learn RL", ["Task1", "Task2"], ["Submit md"])
        assert "# Week 05 Assignment" in text
        assert "1. Task1" in text
        assert "2. Task2" in text


# ═══════════════════════════════════════════════════════════════════════════════
# B1 - Table extraction (clean.py table normalisation)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeTableCell:
    def test_collapses_whitespace(self) -> None:
        assert normalize_table_cell("  hello   world  ") == "hello world"

    def test_empty_cell(self) -> None:
        assert normalize_table_cell("") == ""


class TestNormalizeTableBlocks:
    def test_simple_table_passthrough(self) -> None:
        table = "| A | B |\n| --- | --- |\n| 1 | 2 |\n"
        result = normalize_table_blocks(table)
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result

    def test_inserts_separator_when_missing(self) -> None:
        table = "| A | B |\n| 1 | 2 |\n"
        result = normalize_table_blocks(table)
        assert "---" in result

    def test_normalises_cell_whitespace(self) -> None:
        table = "|  lots   of   spaces  | ok |\n| --- | --- |\n| val | val2 |\n"
        result = normalize_table_blocks(table)
        assert "lots of spaces" in result

    def test_removes_empty_data_table(self) -> None:
        table = "| Header |\n| --- |\n"
        result = normalize_table_blocks(table)
        # Empty data → stripped
        assert "|" not in result

    def test_preserves_non_table_text(self) -> None:
        text = "Hello world\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\nGoodbye\n"
        result = normalize_table_blocks(text)
        assert "Hello world" in result
        assert "Goodbye" in result
        assert "| A | B |" in result

    def test_uneven_columns_padded(self) -> None:
        table = "| A | B | C |\n| --- | --- | --- |\n| 1 | 2 |\n"
        result = normalize_table_blocks(table)
        lines = [line for line in result.strip().split("\n") if line.startswith("|")]
        # Data row should have 3 cols (padded)
        assert lines[-1].count("|") >= 4  # | col | col | col |

    def test_clean_markdown_preserves_tables(self) -> None:
        raw = "## Results\n\n| Method | Score |\n| --- | --- |\n| A | 95 |\n| B | 87 |\n"
        cleaned = clean_markdown(raw)
        assert "| Method | Score |" in cleaned
        assert "| A | 95 |" in cleaned


# ═══════════════════════════════════════════════════════════════════════════════
# B6 - Configurable chunk strategy
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildHeadingRe:
    def test_default_matches_h1_h2(self) -> None:
        regex = build_heading_re()
        assert regex.match("# Title")
        assert regex.match("## Section")
        assert not regex.match("### Sub")

    def test_custom_levels_1_2_3(self) -> None:
        regex = build_heading_re([1, 2, 3])
        assert regex.match("# Title")
        assert regex.match("## Section")
        assert regex.match("### Sub")
        assert not regex.match("#### Deep")

    def test_single_level(self) -> None:
        regex = build_heading_re([1])
        assert regex.match("# Title")
        assert not regex.match("## Section")

    def test_levels_2_3(self) -> None:
        regex = build_heading_re([2, 3])
        assert not regex.match("# Title")
        assert regex.match("## Section")
        assert regex.match("### Sub")


class TestParseChunksWithLevels:
    def test_default_same_as_before(self) -> None:
        text = "# Intro\n\nAlpha\n\n## Part A\n\nBeta\n"
        chunks_default = parse_chunks(text)
        chunks_explicit = parse_chunks(text, split_levels=[1, 2])
        assert len(chunks_default) == len(chunks_explicit)
        assert [c.title for c in chunks_default] == [c.title for c in chunks_explicit]

    def test_three_levels(self) -> None:
        text = "# Ch1\n\nIntro\n\n## Sec1\n\nBody1\n\n### Sub1\n\nDeep\n"
        chunks = parse_chunks(text, split_levels=[1, 2, 3])
        titles = [c.title for c in chunks]
        assert "Ch1" in titles
        assert "Sec1" in titles
        assert "Sub1" in titles

    def test_h3_ignored_in_default(self) -> None:
        text = "# Ch1\n\nIntro\n\n### Sub1\n\nDeep\n"
        chunks = parse_chunks(text)
        # ### not in split levels, so it's body text
        assert len(chunks) == 1
        assert any("### Sub1" in line for line in chunks[0].body)

    def test_single_level_chunks(self) -> None:
        text = "# A\n\nBody A\n\n# B\n\nBody B\n"
        chunks = parse_chunks(text, split_levels=[1])
        assert len(chunks) == 2
        assert chunks[0].title == "A"
        assert chunks[1].title == "B"

    def test_chunk_file_with_split_levels(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# A\n\nBody\n\n## B\n\nMore\n\n### C\n\nDeep\n", encoding="utf-8")
        out = tmp_path / "out"
        chunks = chunk_file(f, out, split_levels=[1, 2, 3])
        assert len(chunks) == 3

    def test_chunk_tree_with_split_levels(self, tmp_path: Path) -> None:
        root = tmp_path / "cleaned" / "project"
        root.mkdir(parents=True)
        (root / "doc.md").write_text("# A\n\nBody\n\n## B\n\nMore\n\n### C\n\nDeep\n", encoding="utf-8")
        out = tmp_path / "chunks"
        written = chunk_tree(root, out, split_levels=[1, 2, 3])
        assert len(written) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# A3 - Formula fidelity scoring
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateFormulaText:
    def test_valid_formula(self) -> None:
        valid, issues = validate_formula_text("q*(a) = E[R_t | A_t = a]")
        assert valid
        assert issues == []

    def test_empty_formula(self) -> None:
        valid, issues = validate_formula_text("")
        assert not valid
        assert "empty" in issues[0]

    def test_no_operators(self) -> None:
        valid, issues = validate_formula_text("just some plain english text")
        assert not valid
        assert any("operator" in i for i in issues)

    def test_unbalanced_parens(self) -> None:
        valid, issues = validate_formula_text("f(x = 3 + 2")
        assert not valid
        assert any("parentheses" in i for i in issues)

    def test_unbalanced_brackets(self) -> None:
        valid, issues = validate_formula_text("E[X = 5")
        assert not valid
        assert any("brackets" in i for i in issues)

    def test_greek_letters_as_operators(self) -> None:
        valid, issues = validate_formula_text("θ")
        assert valid


class TestScoreMarkdown:
    def test_detects_recovered_equations(self) -> None:
        md = "> Equation (recovered from PDF):\n>\n> q*(a) = E[R_t]\n"
        formulas = score_markdown(md)
        assert len(formulas) == 1
        assert formulas[0].kind == "recovered"
        assert formulas[0].valid

    def test_detects_incomplete_equations(self) -> None:
        md = "> Equation present in PDF, but text recovery was incomplete.\n"
        formulas = score_markdown(md)
        assert len(formulas) == 1
        assert formulas[0].kind == "incomplete"
        assert not formulas[0].valid

    def test_detects_placeholders(self) -> None:
        md = "Some text\n\n<!-- formula-not-decoded -->\n\nMore text\n"
        formulas = score_markdown(md)
        assert len(formulas) == 1
        assert formulas[0].kind == "placeholder"

    def test_detects_algorithm_blocks(self) -> None:
        md = "```text\nInitialize Q(s,a)\nLoop for each episode\n```\n"
        formulas = score_markdown(md)
        assert len(formulas) == 1
        assert formulas[0].kind == "algorithm"
        assert formulas[0].valid

    def test_mixed_content(self) -> None:
        md = (
            "> Equation (recovered from PDF):\n>\n> x = 5 + 3\n\n"
            "<!-- formula-not-decoded -->\n\n"
            "> Equation present in PDF, but text recovery was incomplete.\n\n"
            "```text\nAlgorithm step\n```\n"
        )
        formulas = score_markdown(md)
        assert len(formulas) == 4
        kinds = {f.kind for f in formulas}
        assert kinds == {"recovered", "placeholder", "incomplete", "algorithm"}


class TestBuildFileReport:
    def test_fidelity_score(self) -> None:
        md = (
            "> Equation (recovered from PDF):\n>\n> x = y + z\n\n"
            "> Equation present in PDF, but text recovery was incomplete.\n\n"
            "```text\nAlgorithm A\n```\n"
        )
        report = build_file_report(Path("test.md"), md)
        assert report.total_count == 3
        assert report.valid_count == 2
        assert report.fidelity_score == pytest.approx(66.7, abs=0.1)

    def test_no_formulas(self) -> None:
        report = build_file_report(Path("plain.md"), "Just plain text.\n")
        assert report.total_count == 0
        assert report.fidelity_score == 100.0


class TestScoreFile:
    def test_score_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("> Equation (recovered from PDF):\n>\n> a + b = c\n", encoding="utf-8")
        report = score_file(f)
        assert report.recovered_count == 1
        assert report.fidelity_score == 100.0

    def test_score_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            score_file(tmp_path / "nonexistent.md")


class TestScoreTree:
    def test_score_tree(self, tmp_path: Path) -> None:
        root = tmp_path / "docs"
        root.mkdir()
        (root / "a.md").write_text("> Equation (recovered from PDF):\n>\n> x = 1\n", encoding="utf-8")
        (root / "b.md").write_text("<!-- formula-not-decoded -->\n", encoding="utf-8")
        reports = score_tree(root)
        assert len(reports) == 2
        valids = sum(r.valid_count for r in reports)
        assert valids == 1

    def test_score_tree_empty(self, tmp_path: Path) -> None:
        root = tmp_path / "empty"
        root.mkdir()
        with pytest.raises(FileNotFoundError):
            score_tree(root)


class TestWriteReport:
    def test_writes_json(self, tmp_path: Path) -> None:
        reports = [FileReport(file="test.md", recovered_count=2, valid_count=2, total_count=2, fidelity_score=100.0)]
        out = tmp_path / "report.json"
        write_report(reports, out)
        assert out.exists()
        import json

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1
        assert data["summary"]["overall_fidelity"] == 100.0


# ═══════════════════════════════════════════════════════════════════════════════
# Additional coverage - convert.py functions previously untested
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsAlgorithmicText:
    def test_detects_algorithm(self) -> None:
        assert is_algorithmic_text("Algorithm parameter: step size")
        assert is_algorithmic_text("Initialize Q(s,a)")

    def test_rejects_non_algorithm(self) -> None:
        assert not is_algorithmic_text("This is a normal paragraph about control theory.")

    def test_multiple_hints(self) -> None:
        assert is_algorithmic_text("Input: policy π")
        assert is_algorithmic_text("Loop for each episode")
        assert is_algorithmic_text("Choose action a")
        assert is_algorithmic_text("Observe reward r")


class TestFormatIncompleteFormulaBlock:
    def test_output(self) -> None:
        result = format_incomplete_formula_block()
        assert "Equation present in PDF" in result
        assert "recovery was incomplete" in result


class TestDeriveOutputPath:
    def test_simple(self, tmp_path: Path) -> None:
        input_root = tmp_path / "data" / "raw" / "manuscripts"
        input_path = input_root / "paper.pdf"
        output_root = tmp_path / "outputs" / "raw_md"
        result = derive_output_path(input_path, input_root, output_root)
        assert result == output_root / "manuscripts" / "paper.md"

    def test_nested(self, tmp_path: Path) -> None:
        input_root = tmp_path / "data" / "raw" / "books"
        input_path = input_root / "ch1" / "intro.pdf"
        output_root = tmp_path / "outputs" / "raw_md"
        result = derive_output_path(input_path, input_root, output_root)
        assert result == output_root / "books" / "ch1" / "intro.md"


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests - CLI entry points
# ═══════════════════════════════════════════════════════════════════════════════


class TestCleanCLI:
    def test_clean_single_file(self, tmp_path: Path) -> None:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            "course_id: test\npaths:\n  output_raw_md: out\n  output_cleaned_md: out\n"
            "clean:\n  min_repeated_header_count: 3\n  max_repeated_header_length: 80\n"
            "idempotency:\n  enabled: false\nlogging:\n  level: WARNING\n",
            encoding="utf-8",
        )
        inp = tmp_path / "raw.md"
        inp.write_text("## Chapter 1\n\nHello world.\n42\n", encoding="utf-8")
        out_dir = tmp_path / "cleaned"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.clean",
                "--input",
                str(inp),
                "--output-dir",
                str(out_dir),
                "--config",
                str(cfg),
                "--no-manifest",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output_file = out_dir / "raw.md"
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Hello world" in content
        # Page number "42" should be removed
        assert "\n42\n" not in content


class TestChunkCLI:
    def test_chunk_single_file(self, tmp_path: Path) -> None:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            "course_id: test\npaths:\n  output_cleaned_md: out\n  output_chunks: out\n"
            "chunk:\n  split_levels: [1, 2]\n"
            "idempotency:\n  enabled: false\nlogging:\n  level: WARNING\n",
            encoding="utf-8",
        )
        inp = tmp_path / "doc.md"
        inp.write_text("# Intro\n\nParagraph A.\n\n## Details\n\nParagraph B.\n", encoding="utf-8")
        out_dir = tmp_path / "chunks"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.chunk",
                "--input",
                str(inp),
                "--output-dir",
                str(out_dir),
                "--config",
                str(cfg),
                "--no-manifest",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (out_dir / "doc").is_dir()
        chunk_files = list((out_dir / "doc").glob("chunk_*.md"))
        assert len(chunk_files) == 2

    def test_chunk_with_three_levels(self, tmp_path: Path) -> None:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            "course_id: test\npaths:\n  output_cleaned_md: out\n  output_chunks: out\n"
            "chunk:\n  split_levels: [1, 2, 3]\n"
            "idempotency:\n  enabled: false\nlogging:\n  level: WARNING\n",
            encoding="utf-8",
        )
        inp = tmp_path / "doc.md"
        inp.write_text(
            "# Ch1\n\nBody1\n\n## Sec1\n\nBody2\n\n### Sub1\n\nBody3\n",
            encoding="utf-8",
        )
        out_dir = tmp_path / "chunks"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.chunk",
                "--input",
                str(inp),
                "--output-dir",
                str(out_dir),
                "--config",
                str(cfg),
                "--no-manifest",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        chunk_files = list((out_dir / "doc").glob("chunk_*.md"))
        assert len(chunk_files) == 3


class TestFormulaScoreCLI:
    def test_score_single_file(self, tmp_path: Path) -> None:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            "course_id: test\npaths:\n  output_cleaned_md: out\nlogging:\n  level: WARNING\n",
            encoding="utf-8",
        )
        inp = tmp_path / "doc.md"
        inp.write_text(
            "> Equation (recovered from PDF):\n>\n> x + y = z\n\n<!-- formula-not-decoded -->\n",
            encoding="utf-8",
        )
        out = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.formula_score",
                "--input",
                str(inp),
                "--output",
                str(out),
                "--config",
                str(cfg),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert out.exists()
        import json

        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total_formulas"] == 2
        assert data["summary"]["total_valid"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Integration - clean + chunk end-to-end
# ═══════════════════════════════════════════════════════════════════════════════


class TestCleanThenChunkIntegration:
    def test_end_to_end(self, tmp_path: Path) -> None:
        """Run clean_markdown → parse_chunks on realistic content."""
        raw = (
            "## CHAPTER 1 SECTION 1\n\n"
            "Intro paragraph about reinforcement learning fundamentals.\n\n"
            "42\n\n"  # page number
            "## CHAPTER 1 SECTION 2\n\n"
            "Second section discussing policy gradient methods.\n\n"
            "| Method | Score |\n| --- | --- |\n| PPO | 95 |\n| A2C | 87 |\n\n"
            "footer line\nfooter line\nfooter line\n"
        )
        cleaned = clean_markdown(raw)
        # Page number removed
        assert "\n42\n" not in cleaned
        # Table preserved
        assert "| Method | Score |" in cleaned
        # Headings normalised
        assert "# 1" in cleaned

        chunks = parse_chunks(cleaned)
        assert len(chunks) >= 2

    def test_three_level_end_to_end(self, tmp_path: Path) -> None:
        """Clean + chunk with 3 heading levels."""
        raw = "# Introduction\n\nOverview.\n\n## Background\n\nBackground text.\n\n### Details\n\nDetail text.\n"
        cleaned = clean_markdown(raw)
        # Default: 2 levels
        chunks_2 = parse_chunks(cleaned, split_levels=[1, 2])
        chunks_3 = parse_chunks(cleaned, split_levels=[1, 2, 3])
        assert len(chunks_3) >= len(chunks_2)
        assert any(c.title == "Details" for c in chunks_3)


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 2 Tests: Metadata Extraction (A1)
# ══════════════════════════════════════════════════════════════════════════════


class TestExtractTitle:
    def test_from_heading(self) -> None:
        lines = ["# My Research Paper", "", "Abstract..."]
        assert extract_title(lines) == "My Research Paper"

    def test_fallback_to_first_line(self) -> None:
        lines = ["My Research Paper", "", "Abstract..."]
        assert extract_title(lines) == "My Research Paper"

    def test_empty(self) -> None:
        assert extract_title([]) == ""


class TestExtractAuthors:
    def test_comma_separated(self) -> None:
        lines = ["# A Title", "John Doe, Jane Smith, Bob Lee", ""]
        authors = extract_authors(lines)
        assert "John Doe" in authors
        assert "Jane Smith" in authors

    def test_and_separated(self) -> None:
        lines = ["# A Title", "Alice Wang and Bob Chen", ""]
        authors = extract_authors(lines)
        assert "Alice Wang" in authors
        assert "Bob Chen" in authors

    def test_no_authors(self) -> None:
        lines = ["# Title", "", "## Abstract"]
        assert extract_authors(lines) == []


class TestExtractAbstract:
    def test_extracts_abstract(self) -> None:
        text = "# Title\n\nAbstract: This paper explores RL.\n\nKeywords: RL, AI"
        abstract = extract_abstract(text)
        assert "This paper explores RL" in abstract

    def test_no_abstract(self) -> None:
        text = "# Title\n\nSome body text.\n"
        assert extract_abstract(text) == ""


class TestExtractKeywords:
    def test_comma_separated(self) -> None:
        text = "Keywords: reinforcement learning, policy gradient, MDP"
        kws = extract_keywords(text)
        assert "reinforcement learning" in kws
        assert "policy gradient" in kws
        assert len(kws) == 3

    def test_semicolon_separated(self) -> None:
        text = "Keywords: RL; deep learning; optimization"
        kws = extract_keywords(text)
        assert len(kws) == 3

    def test_no_keywords(self) -> None:
        assert extract_keywords("Just a regular paragraph.") == []


class TestExtractDoi:
    def test_finds_doi(self) -> None:
        text = "Available at https://doi.org/10.1234/abcdef.5678 and see also..."
        assert extract_doi(text) == "10.1234/abcdef.5678"

    def test_no_doi(self) -> None:
        assert extract_doi("No DOI in this text.") == ""


class TestExtractYear:
    def test_finds_year(self) -> None:
        text = "Published in 2023 by the IEEE."
        assert extract_year(text) == "2023"

    def test_no_year(self) -> None:
        assert extract_year("No dates here.") == ""


class TestExtractMetadata:
    def test_full_extraction(self) -> None:
        text = (
            "# Deep Reinforcement Learning for Control\n\n"
            "Alice Wang, Bob Chen\n\n"
            "Abstract: We propose a new method for RL.\n\n"
            "Keywords: RL, deep learning, control\n\n"
            "Published in 2024. DOI: 10.1000/test.123\n\n"
            "This work was funded by NSF grant 12345.\n"
        )
        meta = extract_metadata(text, source_file="test.md")
        assert meta.title == "Deep Reinforcement Learning for Control"
        assert len(meta.authors) >= 2
        assert "RL" in meta.keywords
        assert meta.doi == "10.1000/test.123"
        assert meta.year == "2024"
        assert "funded" in meta.funding.lower() or "fund" in meta.funding.lower()
        assert meta.source_file == "test.md"


class TestYAMLFrontmatter:
    def test_basic_output(self) -> None:
        meta = ScholarlyMetadata(title="Test Paper", authors=["A"], year="2024")
        yaml_str = to_yaml_frontmatter(meta)
        assert yaml_str.startswith("---\n")
        assert yaml_str.rstrip().endswith("---")
        assert 'title: "Test Paper"' in yaml_str
        assert 'year: "2024"' in yaml_str


class TestBibtex:
    def test_basic_output(self) -> None:
        meta = ScholarlyMetadata(title="Test Paper", authors=["John Doe"], year="2024", doi="10.1000/test")
        bib = to_bibtex(meta)
        assert "@article{doe2024," in bib
        assert "title = {Test Paper}" in bib
        assert "doi = {10.1000/test}" in bib


class TestAPA7:
    def test_basic_output(self) -> None:
        meta = ScholarlyMetadata(title="Test Paper", authors=["John Doe"], year="2024")
        apa = to_apa7(meta)
        assert "John Doe" in apa
        assert "(2024)" in apa
        assert "Test Paper" in apa


class TestExtractFileAndTree:
    def test_extract_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nBody text.\n", encoding="utf-8")
        meta = extract_file(md)
        assert meta.title == "Title"

    def test_extract_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("# A\n\nBody.\n", encoding="utf-8")
        (d / "b.md").write_text("# B\n\nBody.\n", encoding="utf-8")
        metas = extract_tree(d)
        assert len(metas) == 2

    def test_extract_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            extract_file(tmp_path / "nope.md")

    def test_extract_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            extract_tree(d)


class TestWriteMetadataReport:
    def test_writes_json(self, tmp_path: Path) -> None:
        meta = ScholarlyMetadata(title="Test", year="2024")
        out = tmp_path / "report.json"
        write_metadata_report([meta], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["documents"] == 1
        assert data["entries"][0]["title"] == "Test"


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 2 Tests: RAG Export (C2)
# ══════════════════════════════════════════════════════════════════════════════


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert estimate_tokens("hello world") > 0

    def test_empty(self) -> None:
        assert estimate_tokens("") == 1  # max(1, 0//4)


class TestMakeChunkId:
    def test_deterministic(self) -> None:
        id1 = make_chunk_id("src.md", "Title", 0)
        id2 = make_chunk_id("src.md", "Title", 0)
        assert id1 == id2
        assert len(id1) == 16

    def test_different_inputs(self) -> None:
        id1 = make_chunk_id("a.md", "T1", 0)
        id2 = make_chunk_id("a.md", "T2", 0)
        assert id1 != id2


class TestNormalizeTextForEmbedding:
    def test_collapses_whitespace(self) -> None:
        text = "Hello\n\nWorld\t\tfoo   bar"
        result = normalize_text_for_embedding(text)
        assert result == "Hello World foo bar"

    def test_empty(self) -> None:
        assert normalize_text_for_embedding("") == ""


class TestParseChunkFile:
    def test_basic(self, tmp_path: Path) -> None:
        f = tmp_path / "chunk.md"
        f.write_text("# Chapter 1\n## Section A\n\nBody text.\n", encoding="utf-8")
        rec = parse_chunk_file(f)
        assert rec.title == "Section A"
        assert "Body text" in rec.text
        assert rec.metadata["chapter"] == "Chapter 1"
        assert rec.metadata["section"] == "Section A"

    def test_no_headings(self, tmp_path: Path) -> None:
        f = tmp_path / "chunk.md"
        f.write_text("Just body text.\n", encoding="utf-8")
        rec = parse_chunk_file(f)
        assert rec.title == "chunk"  # falls back to stem
        assert "Just body text" in rec.text


class TestExportFileAndTree:
    def test_export_file(self, tmp_path: Path) -> None:
        f = tmp_path / "chunk.md"
        f.write_text("# Ch\n## Sec\n\nContent here.\n", encoding="utf-8")
        rec = export_file(f)
        assert rec.title == "Sec"
        assert "Content here" in rec.text
        assert rec.metadata["token_estimate"] > 0

    def test_export_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "chunks"
        d.mkdir()
        (d / "a.md").write_text("# A\n\nBody A.\n", encoding="utf-8")
        (d / "b.md").write_text("# B\n\nBody B.\n", encoding="utf-8")
        records = export_tree(d)
        assert len(records) == 2

    def test_export_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            export_file(tmp_path / "nope.md")

    def test_export_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            export_tree(d)


class TestWriteJSONL:
    def test_writes_jsonl(self, tmp_path: Path) -> None:
        records = [
            RAGRecord(id="abc", source="a.md", title="A", text="body1", metadata={}),
            RAGRecord(id="def", source="b.md", title="B", text="body2", metadata={}),
        ]
        out = tmp_path / "output.jsonl"
        write_jsonl(records, out)
        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == "abc"


class TestWriteJSONArray:
    def test_writes_json(self, tmp_path: Path) -> None:
        records = [
            RAGRecord(id="abc", source="a.md", title="A", text="body1", metadata={}),
        ]
        out = tmp_path / "output.json"
        write_json_array(records, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["title"] == "A"


class TestRAGBuildSummary:
    def test_summary(self) -> None:
        records = [
            RAGRecord(id="1", source="a.md", title="A", text="x" * 100, metadata={"token_estimate": 25}),
            RAGRecord(id="2", source="b.md", title="B", text="y" * 200, metadata={"token_estimate": 50}),
        ]
        s = rag_build_summary(records)
        assert s["total_records"] == 2
        assert s["total_tokens_estimate"] == 75
        assert s["sources"] == 2


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 2 Tests: QA Pipeline (C5)
# ══════════════════════════════════════════════════════════════════════════════


class TestCheckEncodingErrors:
    def test_detects_replacement_char(self) -> None:
        text = "Hello \ufffd world"
        issues = check_encoding_errors(text)
        assert any(i.check == "encoding" and i.severity == "error" for i in issues)

    def test_clean_text(self) -> None:
        issues = check_encoding_errors("Hello world")
        assert len(issues) == 0


class TestCheckMissingText:
    def test_short_file(self) -> None:
        issues = check_missing_text("Hi")
        assert any(i.check == "missing_text" for i in issues)

    def test_normal_file(self) -> None:
        issues = check_missing_text("A" * 100)
        assert len(issues) == 0


class TestCheckBrokenLinks:
    def test_broken_link(self) -> None:
        text = "See [here](..)"
        issues = check_broken_links(text)
        assert any(i.check == "broken_link" for i in issues)

    def test_empty_target(self) -> None:
        text = "See [click]()"
        issues = check_broken_links(text)
        assert any(i.check == "broken_link" for i in issues)

    def test_valid_url(self) -> None:
        text = "See [docs](https://example.com)"
        issues = check_broken_links(text)
        assert len(issues) == 0

    def test_anchor_link(self) -> None:
        text = "See [section](#intro)"
        issues = check_broken_links(text)
        assert len(issues) == 0


class TestCheckOrphanHeadings:
    def test_orphan_heading(self) -> None:
        text = "# Title\n## Section\n## Another Section\n\nBody."
        issues = check_orphan_headings(text)
        # "# Title" and "## Section" are orphans (followed by another heading)
        assert any(i.check == "orphan_heading" for i in issues)

    def test_heading_with_body(self) -> None:
        text = "# Title\n\nSome body text.\n"
        issues = check_orphan_headings(text)
        assert len(issues) == 0


class TestCheckTableIntegrity:
    def test_consistent_table(self) -> None:
        text = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        issues = check_table_integrity(text)
        assert len(issues) == 0

    def test_missing_separator(self) -> None:
        text = "| A | B |\n| 1 | 2 |"
        issues = check_table_integrity(text)
        assert any(i.check == "table_integrity" for i in issues)

    def test_inconsistent_columns(self) -> None:
        text = "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |"
        issues = check_table_integrity(text)
        assert any("inconsistent" in i.message for i in issues)


class TestCheckEmptyChunks:
    def test_empty_chunk(self) -> None:
        text = "# Title\n"
        issues = check_empty_chunks(text)
        assert any(i.check == "empty_chunk" for i in issues)

    def test_has_content(self) -> None:
        text = "# Title\n\nThis is a substantial body text for the chunk.\n"
        issues = check_empty_chunks(text)
        assert len(issues) == 0


class TestComputeBadge:
    def test_gold(self) -> None:
        report = FileQAReport(file="test.md", issues=[])
        assert compute_badge(report) == BADGE_GOLD

    def test_fail_on_error(self) -> None:
        from scripts.qa_pipeline import QAIssue

        report = FileQAReport(
            file="test.md",
            issues=[QAIssue(check="enc", severity="error", message="bad")],
        )
        assert compute_badge(report) == BADGE_FAIL

    def test_silver_on_warning(self) -> None:
        from scripts.qa_pipeline import QAIssue

        report = FileQAReport(
            file="test.md",
            issues=[QAIssue(check="x", severity="warning", message="w")],
        )
        assert compute_badge(report) == BADGE_SILVER


class TestComputeOverallBadge:
    def test_all_gold(self) -> None:
        reports = [FileQAReport(file="a.md", badge="gold"), FileQAReport(file="b.md", badge="gold")]
        assert compute_overall_badge(reports) == BADGE_GOLD

    def test_one_fail(self) -> None:
        reports = [FileQAReport(file="a.md", badge="gold"), FileQAReport(file="b.md", badge="fail")]
        assert compute_overall_badge(reports) == BADGE_FAIL

    def test_empty(self) -> None:
        assert compute_overall_badge([]) == BADGE_GOLD


class TestQACheckText:
    def test_clean_text(self) -> None:
        text = "# Title\n\nSome good content here that is long enough.\n"
        issues = qa_check_text(text)
        # Should have no errors (may have orphan heading info)
        assert not any(i.severity == "error" for i in issues)

    def test_problematic_text(self) -> None:
        text = "Broken \ufffd text"
        issues = qa_check_text(text)
        assert any(i.check == "encoding" for i in issues)


class TestQAFileAndTree:
    def test_qa_file(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nGood body text for quality checks.\n", encoding="utf-8")
        report = qa_file(f)
        assert report.file == str(f)
        assert report.badge in ("gold", "silver", "bronze", "fail")

    def test_qa_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("# A\n\nBody text for file A.\n", encoding="utf-8")
        (d / "b.md").write_text("# B\n\nBody text for file B.\n", encoding="utf-8")
        reports = qa_tree(d)
        assert len(reports) == 2

    def test_qa_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            qa_file(tmp_path / "nope.md")

    def test_qa_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            qa_tree(d)


class TestQABuildSummary:
    def test_summary(self) -> None:
        r1 = FileQAReport(file="a.md", badge="gold", issues=[])
        r2 = FileQAReport(file="b.md", badge="silver", issues=[])
        s = build_summary([r1, r2])
        assert s.files_scanned == 2
        assert "gold" in s.badge_distribution


class TestWriteQAReports:
    def test_writes_json(self, tmp_path: Path) -> None:
        r = FileQAReport(file="a.md", badge="gold", issues=[])
        s = build_summary([r])
        out = tmp_path / "qa.json"
        write_qa_report([r], s, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1

    def test_writes_markdown(self, tmp_path: Path) -> None:
        from scripts.qa_pipeline import QAIssue

        issue = QAIssue(check="enc", severity="error", message="bad char", line=5)
        r = FileQAReport(file="a.md", badge="fail", issues=[issue])
        s = build_summary([r])
        out = tmp_path / "qa.md"
        write_markdown_report([r], s, out)
        content = out.read_text(encoding="utf-8")
        assert "Quality Assurance Report" in content
        assert "bad char" in content


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 2 CLI Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMetadataCLI:
    def test_extract_single_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Research Paper\n\nJohn Doe, Jane Smith\n\nAbstract: A study.\n", encoding="utf-8")
        out = tmp_path / "meta.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.metadata", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["documents"] == 1


class TestRAGExportCLI:
    def test_export_single_file(self, tmp_path: Path) -> None:
        md = tmp_path / "chunk.md"
        md.write_text("# Ch\n## Sec\n\nBody.\n", encoding="utf-8")
        out = tmp_path / "out.jsonl"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.rag_export", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        lines = out.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1


class TestQACLI:
    def test_qa_single_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nGood body text for quality checks.\n", encoding="utf-8")
        out = tmp_path / "qa.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.qa_pipeline", "--input", str(md), "--output", str(out), "--format", "json"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 3 - Multi-Format Output (B4)
# ══════════════════════════════════════════════════════════════════════════════


class TestMdToHtml:
    """Tests for Markdown → HTML conversion."""

    def test_heading_conversion(self) -> None:
        result = md_to_html("# Hello World")
        assert "<h1>Hello World</h1>" in result

    def test_h2_and_h3(self) -> None:
        result = md_to_html("## Second\n### Third")
        assert "<h2>Second</h2>" in result
        assert "<h3>Third</h3>" in result

    def test_bold_and_italic(self) -> None:
        result = md_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result

    def test_inline_code(self) -> None:
        result = md_to_html("Use `print()` here")
        assert "<code>print()</code>" in result

    def test_code_block(self) -> None:
        src = "```python\nprint('hi')\n```"
        result = md_to_html(src)
        assert '<pre><code class="language-python">' in result

    def test_link(self) -> None:
        result = md_to_html("[site](https://example.com)")
        assert '<a href="https://example.com">site</a>' in result

    def test_image(self) -> None:
        result = md_to_html("![alt](img.png)")
        assert '<img src="img.png" alt="alt">' in result

    def test_unordered_list(self) -> None:
        result = md_to_html("- item1\n- item2")
        assert "<ul>" in result
        assert "<li>item1</li>" in result

    def test_ordered_list(self) -> None:
        result = md_to_html("1. first\n2. second")
        assert "<li>first</li>" in result

    def test_blockquote(self) -> None:
        result = md_to_html("> quoted text")
        assert "<blockquote>" in result

    def test_horizontal_rule(self) -> None:
        result = md_to_html("---")
        assert "<hr>" in result

    def test_table(self) -> None:
        src = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = md_to_html(src)
        assert "<table>" in result
        assert "<th>" in result
        assert "<td>" in result

    def test_standalone_page_structure(self) -> None:
        result = md_to_html("# Doc", title="My Doc")
        assert "<!DOCTYPE html>" in result
        assert "<title>My Doc</title>" in result
        assert "</html>" in result

    def test_html_escape(self) -> None:
        result = md_to_html("Use <script>alert(1)</script>")
        assert "&lt;script&gt;" in result

    def test_empty_input(self) -> None:
        result = md_to_html("")
        assert "<!DOCTYPE html>" in result


class TestMdToText:
    """Tests for Markdown → plain text."""

    def test_strips_headings(self) -> None:
        result = md_to_text("# Title\n## Sub")
        assert result.startswith("Title\nSub")

    def test_strips_bold_italic(self) -> None:
        result = md_to_text("**bold** and *italic*")
        assert "bold" in result
        assert "italic" in result
        assert "**" not in result

    def test_strips_links(self) -> None:
        result = md_to_text("[text](url)")
        assert "text" in result
        assert "[" not in result

    def test_strips_code_markers(self) -> None:
        result = md_to_text("Use `func()`")
        assert "func()" in result
        assert "`" not in result

    def test_table_pipes_stripped(self) -> None:
        result = md_to_text("| A | B |\n|---|---|\n| 1 | 2 |")
        assert "|" not in result
        assert "A" in result

    def test_code_block_preserved(self) -> None:
        result = md_to_text("```\ncode\n```")
        assert "code" in result

    def test_blockquote_stripped(self) -> None:
        result = md_to_text("> quoted")
        assert "quoted" in result
        assert ">" not in result


class TestMdToYaml:
    """Tests for Markdown → YAML."""

    def test_extracts_title(self) -> None:
        result = md_to_yaml("# My Title\n\nBody text.")
        assert "title: My Title" in result

    def test_includes_body(self) -> None:
        result = md_to_yaml("# T\n\nParagraph here.")
        assert "Paragraph here." in result

    def test_records_headings(self) -> None:
        result = md_to_yaml("# H1\n## H2\n### H3")
        assert "H1" in result
        assert "H2" in result
        assert "H3" in result

    def test_source_field(self) -> None:
        result = md_to_yaml("# T", source="doc.md")
        assert "source: doc.md" in result

    def test_no_title_uses_untitled(self) -> None:
        result = md_to_yaml("Just a paragraph.")
        assert "title: Untitled" in result


class TestMultiFormatConvert:
    """Tests for file/tree conversion."""

    def test_convert_file_html(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nWorld.", encoding="utf-8")
        out = convert_file(md, tmp_path / "out", fmt="html")
        assert out.suffix == ".html"
        assert "Hello" in out.read_text(encoding="utf-8")

    def test_convert_file_text(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\n**bold**", encoding="utf-8")
        out = convert_file(md, tmp_path / "out", fmt="text")
        assert out.suffix == ".txt"
        content = out.read_text(encoding="utf-8")
        assert "Hello" in content
        assert "**" not in content

    def test_convert_file_yaml(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nBody.", encoding="utf-8")
        out = convert_file(md, tmp_path / "out", fmt="yaml")
        assert out.suffix == ".yaml"
        assert "title: Title" in out.read_text(encoding="utf-8")

    def test_convert_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            convert_file(tmp_path / "missing.md", tmp_path / "out")

    def test_convert_file_unsupported_format(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# T", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported format"):
            convert_file(md, tmp_path / "out", fmt="pdf")

    def test_convert_tree(self, tmp_path: Path) -> None:
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "one.md").write_text("# One", encoding="utf-8")
        (tmp_path / "a" / "two.md").write_text("# Two", encoding="utf-8")
        out = tmp_path / "html_out"
        paths = convert_tree(tmp_path / "a", out, fmt="html")
        assert len(paths) == 2
        assert all(p.suffix == ".html" for p in paths)

    def test_convert_tree_empty(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(FileNotFoundError):
            convert_tree(tmp_path / "empty", tmp_path / "out")

    def test_format_extensions(self) -> None:
        assert FORMAT_EXTENSIONS["html"] == ".html"
        assert FORMAT_EXTENSIONS["text"] == ".txt"
        assert FORMAT_EXTENSIONS["yaml"] == ".yaml"


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 3 - GitHub Pages Generator (C1)
# ══════════════════════════════════════════════════════════════════════════════


class TestGHPagesNav:
    """Tests for navigation building."""

    def test_build_nav_html_contains_home(self) -> None:
        pages = [PageEntry(title="Doc1", relative_path="doc1.html", source_md="doc1.md")]
        result = build_nav_html(pages)
        assert "Home" in result
        assert "index.html" in result

    def test_build_nav_highlights_current(self) -> None:
        pages = [PageEntry(title="Doc1", relative_path="doc1.html", source_md="doc1.md")]
        result = build_nav_html(pages, current="doc1.html")
        assert "font-weight:bold" in result

    def test_nav_limits_pages(self) -> None:
        pages = [PageEntry(title=f"D{i}", relative_path=f"d{i}.html", source_md=f"d{i}.md") for i in range(30)]
        result = build_nav_html(pages)
        assert result.count("</a>") <= 21


class TestGHPagesIndex:
    """Tests for index page generation."""

    def test_build_index_page_contains_title(self) -> None:
        pages = [PageEntry(title="Doc", relative_path="doc.html", source_md="doc.md")]
        result = build_index_page("My Site", pages)
        assert "My Site" in result
        assert "<!DOCTYPE html>" in result

    def test_build_index_page_with_description(self) -> None:
        pages = [PageEntry(title="D", relative_path="d.html", source_md="d.md")]
        result = build_index_page("Title", pages, description="Site desc")
        assert "Site desc" in result

    def test_index_page_lists_documents(self) -> None:
        pages = [
            PageEntry(title="Alpha", relative_path="alpha.html", source_md="alpha.md"),
            PageEntry(title="Beta", relative_path="beta.html", source_md="beta.md"),
        ]
        result = build_index_page("Site", pages)
        assert "Alpha" in result
        assert "Beta" in result
        assert 'class="card"' in result

    def test_index_page_escapes_html(self) -> None:
        pages = [PageEntry(title="<script>", relative_path="bad.html", source_md="bad.md")]
        result = build_index_page("Safe", pages)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result


class TestGHPagesDocumentPage:
    """Tests for individual document page generation."""

    def test_document_page_from_markdown(self) -> None:
        page = PageEntry(title="Test", relative_path="test.html", source_md="test.md")
        result = build_document_page(page, "# Test\n\nBody text.", [page])
        assert "Test" in result
        assert "breadcrumb" in result

    def test_document_page_has_nav(self) -> None:
        page = PageEntry(title="P", relative_path="p.html", source_md="p.md")
        result = build_document_page(page, "Content", [page])
        assert "<nav>" in result
        assert "Home" in result

    def test_document_page_has_footer(self) -> None:
        page = PageEntry(title="P", relative_path="p.html", source_md="p.md")
        result = build_document_page(page, "C", [page])
        assert "<footer>" in result


class TestGHPagesSite:
    """Tests for full site generation."""

    def test_collect_pages(self, tmp_path: Path) -> None:
        (tmp_path / "doc1.md").write_text("# Doc One\n\nText.", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "doc2.md").write_text("# Doc Two\n\nText.", encoding="utf-8")
        pages = collect_pages(tmp_path)
        assert len(pages) == 2
        titles = {p.title for p in pages}
        assert "Doc One" in titles
        assert "Doc Two" in titles

    def test_collect_pages_uses_stem_if_no_heading(self, tmp_path: Path) -> None:
        (tmp_path / "noheading.md").write_text("Just text.", encoding="utf-8")
        pages = collect_pages(tmp_path)
        assert pages[0].title == "noheading"

    def test_generate_site(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "doc.md").write_text("# Hello\n\nWorld.", encoding="utf-8")
        out = tmp_path / "site"
        written = generate_site(src, out, site_title="Test Site")
        assert len(written) == 2
        assert (out / "index.html").exists()
        assert (out / "doc.html").exists()

    def test_generate_site_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            generate_site(tmp_path / "missing", tmp_path / "out")

    def test_generate_site_no_md_files(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            generate_site(empty, tmp_path / "out")

    def test_write_site_manifest(self, tmp_path: Path) -> None:
        pages = [
            PageEntry(title="A", relative_path="a.html", source_md="a.md"),
            PageEntry(title="B", relative_path="b.html", source_md="b.md"),
        ]
        out = tmp_path / "manifest.json"
        write_site_manifest(pages, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["pages"] == 2
        assert len(data["entries"]) == 2

    def test_site_preserves_subdirectories(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "sub").mkdir()
        (src / "sub" / "deep.md").write_text("# Deep\n\nContent.", encoding="utf-8")
        out = tmp_path / "site"
        written = generate_site(src, out)
        assert any("sub" in str(p) for p in written)


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 3 - Document-Type Templates (C4)
# ══════════════════════════════════════════════════════════════════════════════


class TestDocTypeDetection:
    """Tests for document type detection."""

    def test_detect_paper(self) -> None:
        text = "# Research\n\nAbstract: Results show...\n\nKeywords: A, B\n\n## References\n\n[1] Smith 2020."
        score, signals = detect_paper(text)
        assert score >= 0.5
        assert any("abstract" in s for s in signals)

    def test_detect_textbook(self) -> None:
        text = "# Chapter 1\n\n" + "Section content. " * 200 + "\n\nExample 1: ...\nExample 2: ...\nExercise 1: ..."
        score, signals = detect_textbook(text)
        assert score >= 0.3

    def test_detect_syllabus(self) -> None:
        text = "# Course Syllabus\n\nInstructor: Prof. Smith\n\nWeek 1: Intro\nWeek 2: Basics\nWeek 3: Advanced\n\nGrading: 40% Midterm"
        score, signals = detect_syllabus(text)
        assert score >= 0.5
        assert any("week" in s for s in signals)

    def test_detect_slides_short_paragraphs(self) -> None:
        text = "# Slide 1\n\n- Point A\n- Point B\n- Point C\n\n# Slide 2\n\n- More\n- Bullets\n- Here\n\n# Slide 3\n\n- Even\n- More\n- Items\n\n# Slide 4\n\n- Final\n- Points"
        score, signals = detect_slides(text)
        assert score >= 0.3

    def test_detect_type_paper(self) -> None:
        text = "# Paper\n\nAbstract: Study results.\n\n10.1234/test\n\n## References\n\n[1] R"
        result = detect_type(text)
        assert result.doc_type == PAPER
        assert result.confidence >= 0.3

    def test_detect_type_generic_fallback(self) -> None:
        text = "This is a regular paragraph of text that does not strongly match any document type. It has some length to avoid the short-paragraph heuristic for slides."
        result = detect_type(text)
        assert result.doc_type == GENERIC

    def test_detect_type_stores_source(self) -> None:
        result = detect_type("Some text", source_file="test.md")
        assert result.source_file == "test.md"

    def test_detect_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nAbstract: Study.\n\n## References\n", encoding="utf-8")
        result = detect_file(md)
        assert isinstance(result, DocTypeResult)

    def test_detect_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            detect_file(tmp_path / "missing.md")

    def test_detect_tree(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# Paper\n\nAbstract: ...\n\n## References\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("Just text.", encoding="utf-8")
        results = detect_tree(tmp_path)
        assert len(results) == 2

    def test_detect_tree_empty(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(FileNotFoundError):
            detect_tree(empty)


class TestDocTypeTemplates:
    """Tests for template operations."""

    def test_all_types_have_template(self) -> None:
        for t in ALL_TYPES:
            template = get_template(t)
            assert template.doc_type == t
            assert len(template.sections) > 0

    def test_get_template_unknown_returns_generic(self) -> None:
        template = get_template("unknown")
        assert template.doc_type == GENERIC

    def test_render_scaffold(self) -> None:
        template = get_template(PAPER)
        scaffold = render_template_scaffold(template)
        assert "## Title" in scaffold or "## Authors" in scaffold
        assert "Document Type: paper" in scaffold

    def test_scaffold_has_all_sections(self) -> None:
        template = get_template(TEXTBOOK)
        scaffold = render_template_scaffold(template)
        for section in template.sections:
            assert f"## {section}" in scaffold


class TestDocTypeReport:
    """Tests for detection report writing."""

    def test_write_detection_report(self, tmp_path: Path) -> None:
        results = [
            DocTypeResult(doc_type=PAPER, confidence=0.8, signals=["has abstract"]),
            DocTypeResult(doc_type=GENERIC, confidence=0.1, signals=["no signals"]),
        ]
        out = tmp_path / "report.json"
        write_detection_report(results, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 2
        assert data["summary"]["type_distribution"]["paper"] == 1
        assert data["summary"]["type_distribution"]["generic"] == 1
        assert len(data["files"]) == 2


# ══════════════════════════════════════════════════════════════════════════════
#  Phase 3 CLI Integration Tests
# ══════════════════════════════════════════════════════════════════════════════


class TestMultiFormatCLI:
    def test_convert_html_cli(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\nWorld.", encoding="utf-8")
        out = tmp_path / "html_out"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.multi_format",
                "--input",
                str(md),
                "--output-dir",
                str(out),
                "--format",
                "html",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (out / "doc.html").exists()

    def test_convert_text_cli(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Hello\n\n**bold**", encoding="utf-8")
        out = tmp_path / "txt_out"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.multi_format",
                "--input",
                str(md),
                "--output-dir",
                str(out),
                "--format",
                "text",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (out / "doc.txt").exists()


class TestGHPagesCLI:
    def test_generate_site_cli(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "doc.md").write_text("# Test\n\nBody.", encoding="utf-8")
        out = tmp_path / "site"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.ghpages",
                "--input",
                str(src),
                "--output-dir",
                str(out),
                "--title",
                "TestSite",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert (out / "index.html").exists()


class TestDocTypeCLI:
    def test_detect_cli(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Paper\n\nAbstract: Results.\n\n## References\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.doc_type", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1

    def test_scaffold_cli(self, tmp_path: Path) -> None:
        out = tmp_path / "scaffold.md"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.doc_type", "--scaffold", "paper", "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        content = out.read_text(encoding="utf-8")
        assert "Document Type: paper" in content


# ═══════════════════════════════════════════════════════════════════════════════
# ocr_quality.py  (Phase 4 — B2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOCRQualityCounters:
    def test_count_garble_chars_clean(self) -> None:
        assert count_garble_chars("Hello, world!") == 0

    def test_count_garble_chars_replacement(self) -> None:
        text = "Hello \ufffd world \x00 end"
        assert count_garble_chars(text) == 2

    def test_count_symbol_soup_clean(self) -> None:
        assert count_symbol_soup("Normal text with punctuation!") == 0

    def test_count_symbol_soup_detected(self) -> None:
        text = "before \u2592\u2593\u2588 after"
        assert count_symbol_soup(text) >= 1

    def test_count_repeat_artefacts_clean(self) -> None:
        assert count_repeat_artefacts("Hello world") == 0

    def test_count_repeat_artefacts_found(self) -> None:
        text = "aaaaaa repeated bbbbbbb"
        assert count_repeat_artefacts(text) >= 1

    def test_count_short_noise_lines_clean(self) -> None:
        text = "Good line\nAnother good line"
        assert count_short_noise_lines(text) == 0

    def test_count_short_noise_lines_noisy(self) -> None:
        text = "Good line\n..\n---\n??\nEnd"
        assert count_short_noise_lines(text) >= 1

    def test_count_common_words(self) -> None:
        text = "The cat is on the mat and the dog is in the house."
        assert count_common_words(text) >= 5


class TestOCRAssessQuality:
    def test_empty_text(self) -> None:
        m = assess_quality("")
        assert m.confidence == 0.0
        assert "empty document" in m.issues

    def test_clean_text_high_confidence(self) -> None:
        text = "The reinforcement learning algorithm converges under the given assumptions. " * 5
        m = assess_quality(text)
        assert m.confidence >= 0.8

    def test_garbled_text_low_confidence(self) -> None:
        text = "\ufffd\x00\ufffd\x01 " * 50 + "real text"
        m = assess_quality(text)
        assert m.confidence < 0.8

    def test_symbol_soup_penalty(self) -> None:
        text = "normal " + "\u2592\u2593\u2588 " * 10 + "text"
        m = assess_quality(text)
        assert m.symbol_soup_count >= 1

    def test_word_count(self) -> None:
        text = "one two three four five"
        m = assess_quality(text)
        assert m.word_count == 5


class TestOCRGrading:
    def test_grade_a(self) -> None:
        assert confidence_to_grade(0.95) == "A"

    def test_grade_b(self) -> None:
        assert confidence_to_grade(0.80) == "B"

    def test_grade_c(self) -> None:
        assert confidence_to_grade(0.65) == "C"

    def test_grade_d(self) -> None:
        assert confidence_to_grade(0.45) == "D"

    def test_grade_f(self) -> None:
        assert confidence_to_grade(0.1) == "F"

    def test_grade_boundary_a(self) -> None:
        assert confidence_to_grade(0.9) == "A"

    def test_grade_boundary_b(self) -> None:
        assert confidence_to_grade(0.75) == "B"


class TestOCRFileOperations:
    def test_assess_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nThe document has normal content here.\n", encoding="utf-8")
        report = assess_file(md)
        assert isinstance(report, OCRFileReport)
        assert report.grade in {"A", "B", "C", "D", "F"}
        assert report.metrics.char_count > 0

    def test_assess_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            assess_file(tmp_path / "nonexistent.md")

    def test_assess_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("The quick brown fox jumps over the lazy dog.\n", encoding="utf-8")
        (d / "b.md").write_text("Another document with normal text in it.\n", encoding="utf-8")
        reports = assess_tree(d)
        assert len(reports) == 2

    def test_assess_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            assess_tree(d)


class TestOCRReportWriter:
    def test_write_ocr_report(self, tmp_path: Path) -> None:
        metrics = OCRQualityMetrics(char_count=100, word_count=20, confidence=0.85)
        report = OCRFileReport(source_file="test.md", metrics=metrics, grade="B")
        out = tmp_path / "report.json"
        write_ocr_report([report], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1
        assert data["summary"]["average_confidence"] == 0.85
        assert data["summary"]["grade_distribution"]["B"] == 1
        assert len(data["files"]) == 1

    def test_write_ocr_report_empty(self, tmp_path: Path) -> None:
        out = tmp_path / "empty.json"
        write_ocr_report([], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 0
        assert data["summary"]["average_confidence"] == 0.0


class TestOCRQualityCLI:
    def test_cli_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\nNormal document content.\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.ocr_quality", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1

    def test_cli_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("Document one with normal text.\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.ocr_quality", "--input", str(d), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════════
# figures.py  (Phase 4 — B3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestFigureExtraction:
    def test_no_figures(self) -> None:
        text = "# Title\n\nJust text, no images."
        entries = extract_figures_from_text(text)
        assert entries == []

    def test_markdown_image(self) -> None:
        text = '![Alt text](images/fig1.png "Title")'
        entries = extract_figures_from_text(text)
        assert len(entries) == 1
        assert entries[0].alt_text == "Alt text"
        assert entries[0].image_path == "images/fig1.png"
        assert entries[0].title == "Title"

    def test_markdown_image_no_title(self) -> None:
        text = "![Diagram](path/diagram.svg)"
        entries = extract_figures_from_text(text)
        assert len(entries) == 1
        assert entries[0].title == ""

    def test_html_image(self) -> None:
        text = '<img src="photo.jpg" alt="Photo">'
        entries = extract_figures_from_text(text)
        assert len(entries) == 1
        assert entries[0].image_path == "photo.jpg"
        assert entries[0].alt_text == "Photo"

    def test_multiple_images(self) -> None:
        text = "![A](a.png)\n\nText\n\n![B](b.png)"
        entries = extract_figures_from_text(text)
        assert len(entries) == 2

    def test_line_numbers(self) -> None:
        text = "Line 1\n![Fig](fig.png)\nLine 3"
        entries = extract_figures_from_text(text)
        assert entries[0].line_number == 2

    def test_exists_check(self, tmp_path: Path) -> None:
        img = tmp_path / "real.png"
        img.write_bytes(b"\x89PNG")
        text = "![Real](real.png)\n![Fake](fake.png)"
        entries = extract_figures_from_text(text, base_dir=tmp_path)
        real = next(e for e in entries if e.image_path == "real.png")
        fake = next(e for e in entries if e.image_path == "fake.png")
        assert real.exists is True
        assert fake.exists is False

    def test_context_capture(self) -> None:
        text = "Line before\n![Fig](fig.png)\nLine after"
        entries = extract_figures_from_text(text)
        assert "Line before" in entries[0].context
        assert "Line after" in entries[0].context


class TestFigureReport:
    def test_build_report_empty(self) -> None:
        report = build_figure_report([])
        assert report.total_figures == 0
        assert report.missing_files == 0

    def test_build_report_with_missing(self) -> None:
        entries = [
            FigureEntry(alt_text="a", image_path="a.png", exists=True),
            FigureEntry(alt_text="b", image_path="b.png", exists=False),
        ]
        report = build_figure_report(entries)
        assert report.total_figures == 2
        assert report.missing_files == 1


class TestFigureFileOps:
    def test_extract_from_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("# Title\n\n![Fig](fig.png)\n", encoding="utf-8")
        report = extract_from_file(md)
        assert report.total_figures == 1

    def test_extract_from_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            extract_from_file(tmp_path / "nonexistent.md")

    def test_extract_from_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("![A](a.png)\n", encoding="utf-8")
        (d / "b.md").write_text("![B](b.png)\n![C](c.png)\n", encoding="utf-8")
        report = extract_from_tree(d)
        assert report.total_figures == 3

    def test_extract_from_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            extract_from_tree(d)


class TestFigureWriters:
    def test_write_manifest(self, tmp_path: Path) -> None:
        entry = FigureEntry(
            alt_text="Test",
            image_path="test.png",
            source_file="doc.md",
            line_number=5,
            exists=True,
        )
        report = FigureReport(total_figures=1, missing_files=0, figures=[entry])
        out = tmp_path / "manifest.json"
        write_figure_manifest(report, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total_figures"] == 1
        assert len(data["figures"]) == 1

    def test_write_gallery(self, tmp_path: Path) -> None:
        entry = FigureEntry(
            alt_text="Fig1",
            image_path="fig1.png",
            source_file="doc.md",
            line_number=1,
            exists=True,
        )
        report = FigureReport(total_figures=1, missing_files=0, figures=[entry])
        out = tmp_path / "gallery.md"
        write_gallery_page(report, out)
        content = out.read_text(encoding="utf-8")
        assert "# Figure Gallery" in content
        assert "fig1.png" in content

    def test_write_gallery_missing(self, tmp_path: Path) -> None:
        entry = FigureEntry(
            alt_text="Missing",
            image_path="gone.png",
            source_file="doc.md",
            line_number=1,
            exists=False,
        )
        report = FigureReport(total_figures=1, missing_files=1, figures=[entry])
        out = tmp_path / "gallery.md"
        write_gallery_page(report, out)
        content = out.read_text(encoding="utf-8")
        assert "MISSING" in content


class TestFigureCLI:
    def test_cli_basic(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("![Fig](fig.png)\n", encoding="utf-8")
        out = tmp_path / "manifest.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.figures", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total_figures"] == 1

    def test_cli_with_gallery(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("![Fig](fig.png)\n", encoding="utf-8")
        out = tmp_path / "manifest.json"
        gallery = tmp_path / "gallery.md"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.figures",
                "--input",
                str(md),
                "--output",
                str(out),
                "--gallery",
                str(gallery),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert gallery.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# parallel.py  (Phase 4 — B5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestParallelConfig:
    def test_defaults(self) -> None:
        cfg = ParallelConfig()
        assert cfg.workers >= 1
        assert cfg.pool_type == "thread"
        assert cfg.timeout is None

    def test_custom(self) -> None:
        cfg = ParallelConfig(workers=4, pool_type="process", timeout=30.0)
        assert cfg.workers == 4
        assert cfg.pool_type == "process"
        assert cfg.timeout == 30.0


class TestTaskResult:
    def test_success(self) -> None:
        r = TaskResult(input_path="a.md", success=True, result="ok", elapsed=0.1)
        assert r.success
        assert r.error == ""

    def test_failure(self) -> None:
        r = TaskResult(input_path="b.md", success=False, error="fail", elapsed=0.2)
        assert not r.success
        assert r.error == "fail"


class TestParallelMap:
    def test_empty_paths(self) -> None:
        report = parallel_map(lambda p: p, [])
        assert report.total == 0

    def test_single_worker(self, tmp_path: Path) -> None:
        files = []
        for i in range(3):
            f = tmp_path / f"doc{i}.md"
            f.write_text(f"content {i}", encoding="utf-8")
            files.append(f)

        def read_len(p: Path) -> int:
            return len(p.read_text(encoding="utf-8"))

        cfg = ParallelConfig(workers=1)
        report = parallel_map(read_len, files, config=cfg)
        assert report.total == 3
        assert report.succeeded == 3
        assert report.failed == 0

    def test_multi_worker(self, tmp_path: Path) -> None:
        files = []
        for i in range(5):
            f = tmp_path / f"doc{i}.md"
            f.write_text(f"content {i}", encoding="utf-8")
            files.append(f)

        def read_len(p: Path) -> int:
            return len(p.read_text(encoding="utf-8"))

        cfg = ParallelConfig(workers=3, pool_type="thread")
        report = parallel_map(read_len, files, config=cfg)
        assert report.total == 5
        assert report.succeeded == 5

    def test_error_handling(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.md"

        def will_fail(p: Path) -> str:
            return p.read_text(encoding="utf-8")

        report = parallel_map(will_fail, [f], config=ParallelConfig(workers=1))
        assert report.total == 1
        assert report.failed == 1
        assert report.results[0].error != ""

    def test_mixed_success_failure(self, tmp_path: Path) -> None:
        good = tmp_path / "good.md"
        good.write_text("ok", encoding="utf-8")
        bad = tmp_path / "bad.md"  # does not exist

        def read_text(p: Path) -> str:
            return p.read_text(encoding="utf-8")

        report = parallel_map(read_text, [good, bad], config=ParallelConfig(workers=1))
        assert report.succeeded == 1
        assert report.failed == 1


class TestCollectMdFiles:
    def test_collects_md(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("A", encoding="utf-8")
        (tmp_path / "b.txt").write_text("B", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "c.md").write_text("C", encoding="utf-8")
        files = collect_md_files(tmp_path)
        names = [f.name for f in files]
        assert "a.md" in names
        assert "c.md" in names
        assert "b.txt" not in names


class TestParallelTree:
    def test_basic(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        for i in range(3):
            (d / f"doc{i}.md").write_text(f"content {i}", encoding="utf-8")

        report = parallel_tree(
            lambda p: len(p.read_text(encoding="utf-8")),
            d,
            config=ParallelConfig(workers=2),
        )
        assert report.total == 3
        assert report.succeeded == 3

    def test_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            parallel_tree(lambda p: p, d)

    def test_custom_glob(self, tmp_path: Path) -> None:
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "a.md").write_text("md", encoding="utf-8")
        (d / "b.txt").write_text("txt", encoding="utf-8")
        report = parallel_tree(
            lambda p: p.suffix,
            d,
            glob="*.txt",
            config=ParallelConfig(workers=1),
        )
        assert report.total == 1

    def test_timing(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("ok", encoding="utf-8")
        report = parallel_tree(
            lambda p: p.name,
            d,
            config=ParallelConfig(workers=1),
        )
        assert report.total_elapsed >= 0


class TestParallelCLI:
    def test_cli_ocr_quality(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("The document content.\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.parallel",
                "--input",
                str(d),
                "--operation",
                "ocr_quality",
                "--workers",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Docker support  (Phase 4 — D4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDockerfiles:
    def test_dockerfile_exists(self) -> None:
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile should exist at project root"

    def test_dockerfile_has_python(self) -> None:
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "python:3.12" in content

    def test_dockerfile_has_entrypoint(self) -> None:
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "ENTRYPOINT" in content

    def test_dockerfile_copies_requirements(self) -> None:
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "requirements.txt" in content

    def test_docker_compose_exists(self) -> None:
        dc = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        assert dc.exists(), "docker-compose.yml should exist at project root"

    def test_docker_compose_services(self) -> None:
        import yaml

        dc = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        data = yaml.safe_load(dc.read_text(encoding="utf-8"))
        assert "services" in data
        assert "pipeline" in data["services"]
        assert "test" in data["services"]

    def test_dockerignore_exists(self) -> None:
        di = Path(__file__).resolve().parent.parent / ".dockerignore"
        assert di.exists(), ".dockerignore should exist at project root"

    def test_dockerignore_excludes_venv(self) -> None:
        di = Path(__file__).resolve().parent.parent / ".dockerignore"
        content = di.read_text(encoding="utf-8")
        assert ".venv" in content


# ═══════════════════════════════════════════════════════════════════════════════
# plugin.py  (Phase 5 — D3)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPluginBase:
    def test_default_hooks_empty(self) -> None:
        p = PluginBase()
        assert p.get_hooks() == []

    def test_info(self) -> None:
        p = PluginBase()
        p.name = "test"
        p.description = "A test plugin"
        info = p.info()
        assert info.name == "test"
        assert info.description == "A test plugin"

    def test_override_detected(self) -> None:
        class MyPlugin(PluginBase):
            name = "my"

            def post_convert(self, context: dict) -> dict:
                context["touched"] = True
                return context

        p = MyPlugin()
        hooks = p.get_hooks()
        assert "post_convert" in hooks
        assert "pre_convert" not in hooks

    def test_context_passthrough(self) -> None:
        p = PluginBase()
        ctx = {"key": "value"}
        result = p.pre_convert(ctx)
        assert result is ctx


class TestPluginRegistry:
    def test_register(self) -> None:
        reg = PluginRegistry()
        p = PluginBase()
        p.name = "test"
        reg.register(p)
        assert len(reg.plugins) == 1

    def test_register_type_error(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(TypeError):
            reg.register("not a plugin")  # type: ignore[arg-type]

    def test_run_hook(self) -> None:
        class Incrementer(PluginBase):
            name = "inc"

            def post_convert(self, context: dict) -> dict:
                context["count"] = context.get("count", 0) + 1
                return context

        reg = PluginRegistry()
        reg.register(Incrementer())
        results = reg.run_hook("post_convert", {"count": 0})
        assert len(results) == 1
        assert results[0].success is True

    def test_run_hook_invalid(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(ValueError):
            reg.run_hook("invalid_hook", {})

    def test_run_hook_error_handling(self) -> None:
        class BadPlugin(PluginBase):
            name = "bad"

            def post_convert(self, context: dict) -> dict:
                raise RuntimeError("boom")

        reg = PluginRegistry()
        reg.register(BadPlugin())
        results = reg.run_hook("post_convert", {})
        assert results[0].success is False
        assert "boom" in results[0].message

    def test_list_plugins(self) -> None:
        reg = PluginRegistry()
        p = PluginBase()
        p.name = "listed"
        reg.register(p)
        infos = reg.list_plugins()
        assert len(infos) == 1
        assert infos[0].name == "listed"

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "plugins"
        d.mkdir()
        reg = PluginRegistry()
        infos = reg.discover(d)
        assert infos == []

    def test_discover_nonexistent_dir(self, tmp_path: Path) -> None:
        reg = PluginRegistry()
        infos = reg.discover(tmp_path / "nope")
        assert infos == []

    def test_discover_plugin_file(self, tmp_path: Path) -> None:
        d = tmp_path / "plugins"
        d.mkdir()
        plugin_py = d / "my_plugin.py"
        plugin_py.write_text(
            "from scripts.plugin import PluginBase\n\n"
            "class MyPlugin(PluginBase):\n"
            "    name = 'discovered'\n"
            "    description = 'Auto-discovered'\n",
            encoding="utf-8",
        )
        reg = PluginRegistry()
        infos = reg.discover(d)
        assert len(infos) == 1
        assert infos[0].name == "discovered"

    def test_discover_skips_underscore(self, tmp_path: Path) -> None:
        d = tmp_path / "plugins"
        d.mkdir()
        (d / "__init__.py").write_text("", encoding="utf-8")
        (d / "_private.py").write_text("x = 1\n", encoding="utf-8")
        reg = PluginRegistry()
        infos = reg.discover(d)
        assert infos == []


class TestPluginReport:
    def test_write_report(self, tmp_path: Path) -> None:
        info = PluginInfo(name="test", description="desc", hooks=["post_convert"])
        out = tmp_path / "plugins.json"
        write_plugin_report([info], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["total_plugins"] == 1
        assert data["plugins"][0]["name"] == "test"


class TestPluginValidHooks:
    def test_all_hooks_exist(self) -> None:
        p = PluginBase()
        for hook in VALID_HOOKS:
            assert hasattr(p, hook)

    def test_hook_count(self) -> None:
        assert len(VALID_HOOKS) == 7


class TestPluginCLI:
    def test_cli_list(self, tmp_path: Path) -> None:
        d = tmp_path / "plugins"
        d.mkdir()
        out = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.plugin",
                "--plugin-dir",
                str(d),
                "--list",
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════════
# citations.py  (Phase 5 — A2)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCitationExtraction:
    def test_no_citations(self) -> None:
        citations = extract_inline_citations("Just plain text.")
        assert citations == []

    def test_author_year_single(self) -> None:
        text = "As shown by (Smith, 2020), the result holds."
        citations = extract_inline_citations(text)
        assert len(citations) == 1
        assert citations[0].cite_type == "author-year"
        assert "Smith" in citations[0].raw_text

    def test_author_year_et_al(self) -> None:
        text = "Results in (Jones et al., 2019) confirm."
        citations = extract_inline_citations(text)
        assert len(citations) == 1

    def test_numeric_single(self) -> None:
        text = "The method [3] is efficient."
        citations = extract_inline_citations(text)
        assert len(citations) == 1
        assert citations[0].cite_type == "numeric"

    def test_numeric_multiple(self) -> None:
        text = "See [1, 2, 3] for details."
        citations = extract_inline_citations(text)
        assert len(citations) == 1
        assert "1" in citations[0].raw_text

    def test_multiple_citations(self) -> None:
        text = "(Smith, 2020) and [5] show this."
        citations = extract_inline_citations(text)
        assert len(citations) == 2

    def test_line_number(self) -> None:
        text = "Line 1\nLine 2\n(Author, 2021) here"
        citations = extract_inline_citations(text)
        assert citations[0].line_number == 3


class TestReferenceExtraction:
    def test_no_references(self) -> None:
        refs = extract_references("Just text, no references section.")
        assert refs == []

    def test_numbered_references(self) -> None:
        text = "# References\n\n[1] Smith J. (2020). A great paper.\n[2] Jones A. (2019). Another paper."
        refs = extract_references(text)
        assert len(refs) == 2
        assert refs[0].key == "1"
        assert refs[1].key == "2"

    def test_author_year_references(self) -> None:
        text = "## References\n\nSmith (2020). A great paper about things.\nJones (2019). Another paper about stuff."
        refs = extract_references(text)
        assert len(refs) >= 1
        assert refs[0].year == "2020"

    def test_doi_extraction(self) -> None:
        text = "# References\n\n[1] Smith (2020). Title. 10.1234/example.2020"
        refs = extract_references(text)
        assert refs[0].doi == "10.1234/example.2020"

    def test_stops_at_next_section(self) -> None:
        text = "## References\n\n[1] First ref.\n\n# Appendix\n\n[2] Not a ref."
        refs = extract_references(text)
        assert len(refs) == 1


class TestCitationGraph:
    def test_empty(self) -> None:
        graph = build_citation_graph([], [])
        assert graph.citations == []
        assert graph.edges == []

    def test_numeric_edges(self) -> None:
        cites = [Citation(raw_text="1, 2", cite_type="numeric")]
        graph = build_citation_graph(cites, [])
        assert len(graph.edges) == 2

    def test_author_year_edges(self) -> None:
        cites = [Citation(raw_text="Smith, 2020", cite_type="author-year")]
        graph = build_citation_graph(cites, [])
        assert len(graph.edges) == 1
        assert graph.edges[0].target_ref == "Smith"

    def test_top_cited(self) -> None:
        cites = [
            Citation(raw_text="1", cite_type="numeric"),
            Citation(raw_text="1", cite_type="numeric"),
            Citation(raw_text="2", cite_type="numeric"),
        ]
        graph = build_citation_graph(cites, [])
        assert graph.top_cited[0] == ("1", 2)


class TestCitationFileOps:
    def test_analyze_file(self, tmp_path: Path) -> None:
        md = tmp_path / "paper.md"
        md.write_text("(Smith, 2020) proved this.\n\n## References\n\n[1] Smith (2020). Paper.\n", encoding="utf-8")
        graph = analyze_file(md)
        assert len(graph.citations) >= 1

    def test_analyze_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            analyze_file(tmp_path / "nope.md")

    def test_analyze_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "papers"
        d.mkdir()
        (d / "a.md").write_text("(Author, 2021) said.\n", encoding="utf-8")
        (d / "b.md").write_text("[1] cited.\n", encoding="utf-8")
        graph = analyze_tree(d)
        assert len(graph.citations) >= 1

    def test_analyze_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            analyze_tree(d)


class TestCitationWriters:
    def test_write_report(self, tmp_path: Path) -> None:
        graph = CitationGraph(
            citations=[Citation(raw_text="Smith, 2020", cite_type="author-year")],
            references=[Reference(key="1", raw_text="Smith (2020). Paper.")],
            edges=[CitationEdge(source_doc="doc.md", target_ref="Smith")],
            top_cited=[("Smith", 1)],
        )
        out = tmp_path / "citations.json"
        write_citation_report(graph, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["total_citations"] == 1
        assert data["summary"]["total_references"] == 1

    def test_write_dot(self, tmp_path: Path) -> None:
        graph = CitationGraph(
            edges=[CitationEdge(source_doc="doc.md", target_ref="ref1")],
        )
        out = tmp_path / "graph.dot"
        write_dot_graph(graph, out)
        content = out.read_text(encoding="utf-8")
        assert "digraph citations" in content
        assert "doc.md" in content
        assert "ref1" in content


class TestCitationCLI:
    def test_cli_basic(self, tmp_path: Path) -> None:
        md = tmp_path / "paper.md"
        md.write_text("(Smith, 2020) here.\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.citations", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "summary" in data


# ═══════════════════════════════════════════════════════════════════════════════
# topics.py  (Phase 5 — A4)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTopicClassification:
    def test_empty_text(self) -> None:
        result = classify_text("")
        assert result.primary_topic == "generic"
        assert result.word_count == 0

    def test_rl_text(self) -> None:
        text = (
            "Reinforcement learning uses a Markov decision process. "
            "The policy gradient method optimizes the reward. "
            "Q-learning and temporal difference are key algorithms."
        )
        result = classify_text(text)
        assert result.primary_topic == "reinforcement_learning"
        assert result.confidence > 0

    def test_ml_text(self) -> None:
        text = (
            "Machine learning with neural network and deep learning. "
            "Classification via supervised learning and gradient descent. "
            "We avoid overfitting with cross-validation."
        )
        result = classify_text(text)
        assert result.primary_topic == "machine_learning"

    def test_nlp_text(self) -> None:
        text = (
            "Natural language processing uses transformer attention mechanism. "
            "BERT and GPT are language model architectures. "
            "Tokenization and word embedding are preprocessing steps."
        )
        result = classify_text(text)
        assert result.primary_topic == "nlp"

    def test_generic_fallback(self) -> None:
        text = "The quick brown fox jumps over the lazy dog repeatedly many times."
        result = classify_text(text)
        assert result.primary_topic == "generic"
        assert result.confidence == 0

    def test_scores_sorted(self) -> None:
        text = "Reinforcement learning MDP policy gradient. Also mentions machine learning neural network."
        result = classify_text(text)
        if len(result.scores) >= 2:
            assert result.scores[0].score >= result.scores[1].score


class TestTopicScore:
    def test_dataclass(self) -> None:
        ts = TopicScore(topic="ml", score=5.0, keyword_hits=3)
        assert ts.topic == "ml"
        assert ts.keyword_hits == 3


class TestGetTopTopics:
    def test_top_n(self) -> None:
        doc = DocumentTopics(
            source_file="test.md",
            word_count=100,
            scores=[
                TopicScore(topic="a", score=10.0, keyword_hits=5),
                TopicScore(topic="b", score=8.0, keyword_hits=4),
                TopicScore(topic="c", score=3.0, keyword_hits=2),
            ],
        )
        assert get_top_topics(doc, 2) == ["a", "b"]

    def test_top_n_fewer(self) -> None:
        doc = DocumentTopics(
            source_file="",
            word_count=10,
            scores=[
                TopicScore(topic="x", score=1.0, keyword_hits=1),
            ],
        )
        assert get_top_topics(doc, 5) == ["x"]


class TestTopicKeywords:
    def test_keywords_exist(self) -> None:
        assert "reinforcement_learning" in TOPIC_KEYWORDS
        assert "machine_learning" in TOPIC_KEYWORDS
        assert len(TOPIC_KEYWORDS) >= 9

    def test_keywords_non_empty(self) -> None:
        for topic, kws in TOPIC_KEYWORDS.items():
            assert len(kws) > 0, f"No keywords for {topic}"


class TestTopicFileOps:
    def test_classify_file(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("Reinforcement learning with policy gradient and MDP.\n", encoding="utf-8")
        result = classify_file(md)
        assert result.primary_topic == "reinforcement_learning"

    def test_classify_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            classify_file(tmp_path / "nope.md")

    def test_classify_tree(self, tmp_path: Path) -> None:
        d = tmp_path / "docs"
        d.mkdir()
        (d / "a.md").write_text("Machine learning neural network classification.\n", encoding="utf-8")
        (d / "b.md").write_text("Statistics and probability distribution.\n", encoding="utf-8")
        results = classify_tree(d)
        assert len(results) == 2

    def test_classify_tree_empty(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        with pytest.raises(FileNotFoundError):
            classify_tree(d)


class TestTopicDistribution:
    def test_distribution(self) -> None:
        results = [
            DocumentTopics(source_file="a", word_count=100, primary_topic="ml"),
            DocumentTopics(source_file="b", word_count=100, primary_topic="ml"),
            DocumentTopics(source_file="c", word_count=100, primary_topic="nlp"),
        ]
        dist = build_topic_distribution(results)
        assert dist["ml"] == 2
        assert dist["nlp"] == 1


class TestTopicReport:
    def test_write_report(self, tmp_path: Path) -> None:
        result = DocumentTopics(
            source_file="doc.md",
            word_count=50,
            primary_topic="ml",
            confidence=0.8,
        )
        out = tmp_path / "topics.json"
        write_topic_report([result], out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1
        assert "ml" in data["summary"]["topic_distribution"]


class TestTopicCLI:
    def test_cli_basic(self, tmp_path: Path) -> None:
        md = tmp_path / "doc.md"
        md.write_text("Reinforcement learning and policy gradient.\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.topics", "--input", str(md), "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_scanned"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# diff.py  (Phase 5 — B7)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDiffTexts:
    def test_identical(self) -> None:
        fd = diff_texts("hello\n", "hello\n", label="test")
        assert fd.status == "unchanged"
        assert fd.lines_added == 0
        assert fd.lines_removed == 0

    def test_modified(self) -> None:
        fd = diff_texts("line1\nline2\n", "line1\nline3\n", label="test")
        assert fd.status == "modified"
        assert fd.lines_added >= 1
        assert fd.lines_removed >= 1

    def test_additions(self) -> None:
        fd = diff_texts("a\n", "a\nb\nc\n", label="test")
        assert fd.status == "modified"
        assert fd.lines_added >= 2

    def test_removals(self) -> None:
        fd = diff_texts("a\nb\nc\n", "a\n", label="test")
        assert fd.status == "modified"
        assert fd.lines_removed >= 2

    def test_diff_text_content(self) -> None:
        fd = diff_texts("old\n", "new\n", label="f.md")
        assert "old/" in fd.diff_text
        assert "new/" in fd.diff_text


class TestDiffFiles:
    def test_both_exist(self, tmp_path: Path) -> None:
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text("line1\n", encoding="utf-8")
        new.write_text("line2\n", encoding="utf-8")
        fd = diff_files(old, new)
        assert fd.status == "modified"

    def test_old_missing(self, tmp_path: Path) -> None:
        new = tmp_path / "new.md"
        new.write_text("content\n", encoding="utf-8")
        fd = diff_files(tmp_path / "nope.md", new)
        assert fd.status == "added"
        assert fd.lines_added >= 1

    def test_new_missing(self, tmp_path: Path) -> None:
        old = tmp_path / "old.md"
        old.write_text("content\n", encoding="utf-8")
        fd = diff_files(old, tmp_path / "nope.md")
        assert fd.status == "removed"
        assert fd.lines_removed >= 1

    def test_identical_files(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.md"
        f2 = tmp_path / "b.md"
        f1.write_text("same\n", encoding="utf-8")
        f2.write_text("same\n", encoding="utf-8")
        fd = diff_files(f1, f2)
        assert fd.status == "unchanged"


class TestDiffTrees:
    def test_identical_trees(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "a.md").write_text("same\n", encoding="utf-8")
        (new / "a.md").write_text("same\n", encoding="utf-8")
        td = diff_trees(old, new)
        assert len(td.files_unchanged) == 1
        assert len(td.files_modified) == 0

    def test_added_file(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (new / "added.md").write_text("new content\n", encoding="utf-8")
        td = diff_trees(old, new)
        assert "added.md" in td.files_added

    def test_removed_file(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "gone.md").write_text("old content\n", encoding="utf-8")
        td = diff_trees(old, new)
        assert "gone.md" in td.files_removed

    def test_modified_file(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "doc.md").write_text("version 1\n", encoding="utf-8")
        (new / "doc.md").write_text("version 2\n", encoding="utf-8")
        td = diff_trees(old, new)
        assert "doc.md" in td.files_modified

    def test_totals(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "a.md").write_text("line1\nline2\n", encoding="utf-8")
        (new / "a.md").write_text("line1\nchanged\nextra\n", encoding="utf-8")
        td = diff_trees(old, new)
        assert td.total_lines_added >= 1

    def test_subdirectories(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        (old / "sub").mkdir(parents=True)
        (new / "sub").mkdir(parents=True)
        (old / "sub" / "deep.md").write_text("v1\n", encoding="utf-8")
        (new / "sub" / "deep.md").write_text("v2\n", encoding="utf-8")
        td = diff_trees(old, new)
        assert len(td.files_modified) == 1


class TestDiffReportWriters:
    def test_write_diff_report(self, tmp_path: Path) -> None:
        td = TreeDiff(
            files_added=["new.md"],
            files_modified=["changed.md"],
            total_lines_added=10,
            total_lines_removed=5,
            file_diffs=[
                FileDiff(file_path="new.md", status="added", lines_added=10),
                FileDiff(file_path="changed.md", status="modified", lines_added=5, lines_removed=5),
            ],
        )
        out = tmp_path / "diff.json"
        write_diff_report(td, out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["summary"]["files_added"] == 1
        assert data["summary"]["files_modified"] == 1
        assert data["summary"]["total_lines_added"] == 10

    def test_write_unified_diff(self, tmp_path: Path) -> None:
        td = TreeDiff(
            file_diffs=[
                FileDiff(file_path="a.md", status="modified", diff_text="--- a\n+++ b\n-old\n+new\n"),
            ],
        )
        out = tmp_path / "diff.txt"
        write_unified_diff(td, out)
        content = out.read_text(encoding="utf-8")
        assert "---" in content

    def test_write_unified_empty(self, tmp_path: Path) -> None:
        td = TreeDiff()
        out = tmp_path / "empty.txt"
        write_unified_diff(td, out)
        assert out.exists()


class TestDiffCLI:
    def test_cli_dirs(self, tmp_path: Path) -> None:
        old = tmp_path / "old"
        new = tmp_path / "new"
        old.mkdir()
        new.mkdir()
        (old / "a.md").write_text("v1\n", encoding="utf-8")
        (new / "a.md").write_text("v2\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.diff",
                "--old",
                str(old),
                "--new",
                str(new),
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "summary" in data


# ═══════════════════════════════════════════════════════════════════════════════
# run_pipeline.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildParser:
    """Test argument parsing for the pipeline orchestrator."""

    def test_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.stages == ["convert", "clean", "chunk", "render"]
        assert args.engine is None
        assert args.no_manifest is False
        assert args.config is None

    def test_single_stage(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--stages", "convert"])
        assert args.stages == ["convert"]

    def test_multiple_stages(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--stages", "convert", "clean"])
        assert args.stages == ["convert", "clean"]

    def test_invalid_stage_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--stages", "nonexistent"])

    def test_engine_choices(self) -> None:
        parser = build_parser()
        for engine in ("docling", "markitdown", "dual"):
            args = parser.parse_args(["--engine", engine])
            assert args.engine == engine

    def test_invalid_engine_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--engine", "imaginary"])

    def test_no_manifest_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--no-manifest"])
        assert args.no_manifest is True

    def test_config_path(self, tmp_path: Path) -> None:
        cfg = tmp_path / "custom.yaml"
        cfg.touch()
        parser = build_parser()
        args = parser.parse_args(["--config", str(cfg)])
        assert args.config == cfg

    def test_combined_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--stages", "clean", "chunk", "--engine", "docling", "--no-manifest"])
        assert args.stages == ["clean", "chunk"]
        assert args.engine == "docling"
        assert args.no_manifest is True


class TestRunPipelineCLI:
    """Test the pipeline CLI via subprocess."""

    @staticmethod
    def _write_config(tmp_path: Path) -> Path:
        cfg = tmp_path / "cfg.yaml"
        cfg.write_text(
            "course_id: test\n"
            "paths:\n"
            "  data_raw: {d}\n"
            "  output_raw_md: {r}\n"
            "  output_cleaned_md: {c}\n"
            "  output_chunks: {k}\n"
            "convert:\n"
            "  engine: dual\n"
            "idempotency:\n"
            "  enabled: false\n"
            "logging:\n"
            "  level: WARNING\n".format(
                d=tmp_path / "data",
                r=tmp_path / "raw_md",
                c=tmp_path / "cleaned_md",
                k=tmp_path / "chunks",
            ),
            encoding="utf-8",
        )
        for d in ("data/test", "raw_md/test", "cleaned_md/test", "chunks/test"):
            (tmp_path / d).mkdir(parents=True, exist_ok=True)
        return cfg

    def test_cli_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.run_pipeline", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "pdf-to-markdown pipeline" in result.stdout.lower()

    def test_cli_unknown_arg(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.run_pipeline", "--unknown-flag"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_cli_missing_config(self, tmp_path: Path) -> None:
        bad_cfg = tmp_path / "nonexistent.yaml"
        result = subprocess.run(
            [sys.executable, "-m", "scripts.run_pipeline", "--config", str(bad_cfg)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_cli_clean_stage_on_empty_dir(self, tmp_path: Path) -> None:
        cfg = self._write_config(tmp_path)
        # Place a dummy markdown so clean_tree finds something
        (tmp_path / "raw_md" / "test" / "doc.md").write_text("# Title\n\nBody.\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.run_pipeline",
                "--config",
                str(cfg),
                "--stages",
                "clean",
                "--no-manifest",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_cli_chunk_stage_on_empty_dir(self, tmp_path: Path) -> None:
        cfg = self._write_config(tmp_path)
        # Place a dummy cleaned markdown so chunk_tree finds something
        (tmp_path / "cleaned_md" / "test" / "doc.md").write_text("# Chapter\n\nContent.\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.run_pipeline",
                "--config",
                str(cfg),
                "--stages",
                "chunk",
                "--no-manifest",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_cli_files(self, tmp_path: Path) -> None:
        old = tmp_path / "old.md"
        new = tmp_path / "new.md"
        old.write_text("old content\n", encoding="utf-8")
        new.write_text("new content\n", encoding="utf-8")
        out = tmp_path / "report.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.diff",
                "--old",
                str(old),
                "--new",
                str(new),
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════════
# D2: py.typed marker  (Phase 5)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPyTyped:
    def test_py_typed_exists(self) -> None:
        marker = Path(__file__).resolve().parent.parent / "scripts" / "py.typed"
        assert marker.exists(), "py.typed marker should exist in scripts/"

    def test_pyrightconfig_exists(self) -> None:
        cfg = Path(__file__).resolve().parent.parent / "pyrightconfig.json"
        assert cfg.exists()

    def test_pyrightconfig_has_standard(self) -> None:
        cfg = Path(__file__).resolve().parent.parent / "pyrightconfig.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data.get("typeCheckingMode") == "standard"
