from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from phinitelab_pdf_pipeline.common import load_config, resolve_path, setup_logging

WEEK_HEADING_RE = re.compile(r"^##\s+Week\s+(\d+)\s*:\s*(.+?)\s*$", re.IGNORECASE)
LINE_VALUE_RE_TEMPLATE = r"(?m)^(?:##\s+)?{label}:\s*(.+?)\s*$"
ACRONYMS = {"rl": "RL", "mdp": "MDP", "td": "TD", "hjb": "HJB", "pg": "PG"}


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return path.read_text(encoding="utf-8")


def extract_line_value(text: str, label: str, fallback: str) -> str:
    match = re.search(LINE_VALUE_RE_TEMPLATE.format(label=re.escape(label)), text)
    return match.group(1).strip() if match else fallback


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"(?ms)^##\s+{re.escape(heading)}:?\s*$\n(.*?)(?=^##\s+|\Z)",
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def clean_inline(text: str) -> str:
    return " ".join(text.replace("\n", " ").split())


def bullet_lines_from_section(section: str) -> list[str]:
    lines: list[str] = []
    for raw_line in section.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines


def headings_from_markdown(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = re.sub(r"^\s*#{1,6}\s*", "", stripped).strip()
            if title:
                headings.append(title)
    return headings


def paragraphs_from_markdown(text: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                paragraphs.append(clean_inline(" ".join(current)))
                current = []
            continue
        if stripped.startswith("#"):
            if current:
                paragraphs.append(clean_inline(" ".join(current)))
                current = []
            continue
        current.append(stripped)
    if current:
        paragraphs.append(clean_inline(" ".join(current)))
    return paragraphs


def humanize_topic(slug: str) -> str:
    parts = slug.split("_")
    if parts and parts[0].isdigit():
        parts = parts[1:]
    rendered: list[str] = []
    for part in parts:
        lowered = part.lower()
        rendered.append(ACRONYMS.get(lowered, lowered.capitalize()))
    return " ".join(rendered) if rendered else slug


def parse_week_entries(syllabus_text: str) -> dict[int, dict[str, list[str] | str]]:
    lines = syllabus_text.splitlines()
    entries: dict[int, dict[str, list[str] | str]] = {}
    current_week: int | None = None
    current_title = ""
    current_bullets: list[str] = []

    def flush() -> None:
        nonlocal current_week, current_title, current_bullets
        if current_week is not None:
            entries[current_week] = {
                "title": clean_inline(current_title),
                "bullets": [clean_inline(item) for item in current_bullets if item.strip()],
            }
        current_week = None
        current_title = ""
        current_bullets = []

    for line in lines:
        heading_match = WEEK_HEADING_RE.match(line.strip())
        if heading_match:
            flush()
            current_week = int(heading_match.group(1))
            current_title = heading_match.group(2).strip()
            continue
        if current_week is None:
            continue
        stripped = line.strip()
        if stripped.startswith("## "):
            flush()
            continue
        if stripped.startswith("- "):
            current_bullets.append(stripped[2:].strip())

    flush()
    return entries


def extract_programs(section: str) -> list[str]:
    bullets = bullet_lines_from_section(section)
    if bullets:
        parts: list[str] = []
        for bullet in bullets:
            parts.extend(item.strip() for item in bullet.split(",") if item.strip())
        return parts
    if section:
        return [item.strip() for item in section.split(",") if item.strip()]
    return []


def first_items(values: list[str], limit: int) -> list[str]:
    unique: list[str] = []
    for value in values:
        stripped = clean_inline(value)
        if stripped and stripped not in unique:
            unique.append(stripped)
        if len(unique) >= limit:
            break
    return unique


def summarize_text(text: str, max_chars: int = 240) -> str:
    cleaned = clean_inline(text)
    if len(cleaned) <= max_chars:
        return cleaned
    sentence_match = re.match(rf"^(.{{0,{max_chars}}}?[.!?])(?:\s|$)", cleaned)
    if sentence_match:
        return sentence_match.group(1).strip()
    return cleaned[: max_chars - 1].rstrip() + "…"


def build_course_profile_text(
    course_title: str,
    semester: str,
    instructor: str,
    main_topics: list[str],
    programs: list[str],
    notes: list[str],
) -> str:
    lines = [
        "# Course Profile",
        "",
        "## Course Name",
        course_title,
        "",
        "## Semester",
        semester,
        "",
        "## Instructor",
        instructor,
        "",
        "## Main Topics",
    ]
    lines.extend(f"- {topic}" for topic in main_topics)
    lines.extend(["", "## Programming Tools"])
    lines.extend(f"- {program}" for program in programs)
    lines.extend(["", "## Notes"])
    lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines).strip() + "\n"


def build_global_rules_text(existing_rules: list[str], ai_rules: list[str], admin_rules: list[str]) -> str:
    lines = ["# Global Rules", ""]
    for rule in first_items(existing_rules + ai_rules + admin_rules, limit=12):
        lines.append(f"- {rule}")
    return "\n".join(lines).strip() + "\n"


def build_week_rules_text(
    week_number: int,
    title: str,
    scope_items: list[str],
    exclude_items: list[str],
    output_items: list[str],
    *,
    max_scope: int = 6,
) -> str:
    lines = [
        f"# Week {week_number:02d} Rules",
        "",
        "## Scope",
    ]
    lines.extend(f"- {item}" for item in first_items(scope_items, limit=max_scope))
    lines.extend(["", "## Exclude"])
    lines.extend(f"- {item}" for item in first_items(exclude_items, limit=5))
    lines.extend(["", "## Output"])
    lines.extend(f"- {item}" for item in first_items(output_items, limit=5))
    return "\n".join(lines).strip() + "\n"


def build_assignment_text(
    week_number: int,
    objective: str,
    tasks: list[str],
    submission: list[str],
    *,
    max_tasks: int = 5,
) -> str:
    lines = [
        f"# Week {week_number:02d} Assignment",
        "",
        "## Objective",
        objective,
        "",
        "## Tasks",
    ]
    lines.extend(f"{index + 1}. {task}" for index, task in enumerate(first_items(tasks, limit=max_tasks)))
    lines.extend(["", "## Submission"])
    lines.extend(f"- {item}" for item in first_items(submission, limit=4))
    return "\n".join(lines).strip() + "\n"


def render_meta_templates(
    course_root: Path,
    syllabus_text: str,
    week_entries: dict[int, dict[str, list[str] | str]],
) -> list[Path]:
    course_title = extract_line_value(syllabus_text, "Course Title", fallback=course_root.name)
    instructor = extract_line_value(syllabus_text, "Instructor", fallback="Belirtilmemiş")
    classroom_code = extract_line_value(syllabus_text, "Classroom Code", fallback="Belirtilmemiş")
    programs = extract_programs(extract_section(syllabus_text, "Required Programs"))
    assessment = bullet_lines_from_section(extract_section(syllabus_text, "Assessment"))
    if not assessment:
        assessment = [
            clean_inline(line) for line in extract_section(syllabus_text, "Assessment").splitlines() if line.strip()
        ]

    main_topics = []
    for entry in week_entries.values():
        title = str(entry["title"])
        if "(Synchronous)" in title:
            continue
        main_topics.append(title)
    main_topics = first_items(main_topics, limit=8)

    ai_section = extract_section(syllabus_text, "Use of an Instructor-Developed LLM-Based AI System")
    other_rules = extract_section(syllabus_text, "Other Rules")
    ai_rules = bullet_lines_from_section(ai_section)
    admin_rules = bullet_lines_from_section(other_rules)

    notes = [
        f"Classroom Code: {classroom_code}",
        "Assessment: " + "; ".join(assessment) if assessment else "Assessment bilgisi bulunamadı.",
        "Bu profil ve hafta şablonları syllabus ve hafta içeriklerinden deterministik olarak dolduruldu.",
    ]

    course_profile_path = course_root / "00_meta" / "course_profile.md"
    course_profile_path.parent.mkdir(parents=True, exist_ok=True)
    course_profile_path.write_text(
        build_course_profile_text(
            course_title=course_title,
            semester="Belirtilmemiş",
            instructor=instructor,
            main_topics=main_topics,
            programs=programs or ["Belirtilmemiş"],
            notes=notes,
        ),
        encoding="utf-8",
    )

    global_rules_path = course_root / "00_meta" / "global_rules.md"
    existing_rules = [
        "Yanıt dili Türkçe olmalı",
        "Sadece ilgili hafta kullanılmalı",
        "Haftalar karıştırılmamalı",
        "Pedagojik çıktı üretilmeli",
        "Gereksiz genişletme yapılmamalı",
    ]
    global_rules_path.write_text(
        build_global_rules_text(existing_rules=existing_rules, ai_rules=ai_rules, admin_rules=admin_rules),
        encoding="utf-8",
    )
    return [course_profile_path, global_rules_path]


def render_week_templates(
    course_root: Path,
    raw_root: Path,
    cleaned_root: Path,
    week_entries: dict[int, dict[str, list[str] | str]],
    *,
    cfg: dict[str, Any] | None = None,
) -> list[Path]:
    rt_cfg = (cfg or {}).get("render_templates", {})
    max_summary = rt_cfg.get("max_summary_chars", 240)
    max_scope = rt_cfg.get("max_scope_items", 6)
    max_tasks = rt_cfg.get("max_tasks", 5)

    written: list[Path] = []
    for week_dir in sorted(p for p in course_root.iterdir() if p.is_dir() and p.name != "00_meta"):
        week_prefix = week_dir.name.split("_", 1)[0]
        if not week_prefix.isdigit():
            continue
        week_number = int(week_prefix)
        week_entry = week_entries.get(week_number, {})
        week_title = str(week_entry.get("title", humanize_topic(week_dir.name)))
        week_bullets = [str(item) for item in week_entry.get("bullets", [])]

        raw_content_path = raw_root / week_dir.name / "content.md"
        cleaned_content_path = cleaned_root / week_dir.name / "content.md"
        content_text = read_text(raw_content_path) if raw_content_path.exists() else ""
        if not content_text and cleaned_content_path.exists():
            content_text = read_text(cleaned_content_path)
        content_headings = [
            heading
            for heading in headings_from_markdown(content_text)
            if not re.fullmatch(r"Chapter\s+\d+", heading, flags=re.IGNORECASE)
        ]
        content_paragraphs = paragraphs_from_markdown(content_text)

        scope_items = [
            f"Ana odak: {week_title}",
            *week_bullets,
            *content_headings[:3],
        ]
        exclude_items = [
            "İlgisiz haftaların kavramları ve algoritmaları",
            "Belgede geçmeyen gereksiz yan konular",
            "Kanıtsız veya kaynak dışı iddialar",
            "Konu dışı araç ve framework tartışmaları",
        ]
        output_items = [
            "Türkçe, kısa ve pedagojik açıklama üret",
            "Gerekli olduğunda denklem, algoritma veya adım dizisini açıkça yaz",
            "Haftanın ana kavramlarını birbirine bağlayan yapılandırılmış özet ver",
            "Kod haftalarında çözümü codes/ klasörüyle uyumlu düşün",
        ]

        objective_source = content_paragraphs[0] if content_paragraphs else ""
        if objective_source:
            objective = (
                f"Bu haftada {week_title} konusunu çalış ve şu çerçeveyi temel al: "
                f"{summarize_text(objective_source, max_chars=max_summary)}"
            )
        else:
            objective = (
                f"Bu haftada {week_title} konusunu syllabus kapsamına bağlı kalarak açıklayıp uygulamaya dönüştür."
            )

        task_seed = week_bullets or content_headings or [week_title]
        tasks = [
            f"{item} başlığını kısa ama teknik olarak doğru biçimde açıkla." for item in first_items(task_seed, limit=3)
        ]
        if "coding" in week_dir.name:
            tasks.append("Haftanın ana fikrini gösterecek küçük bir kod iskeleti veya pseudocode üret.")
        else:
            tasks.append("Kavramsal akışı bir örnek veya mini senaryo ile somutlaştır.")
        tasks.append("Öğrenme çıktısını en fazla birkaç alt başlıkta yapılandırılmış biçimde teslim et.")

        submission = [
            "Tek bir düzenli Markdown çıktı hazırla.",
            "Kullanılan kavramları haftanın kapsamıyla sınırlı tut.",
            "Kod haftalarında gerekli ise ilgili dosyaları codes/ altına yerleştir.",
            "Teslimde kısa özet + ana kavramlar + gerekiyorsa örnek çözüm bulunsun.",
        ]

        rules_path = week_dir / "rules.md"
        rules_path.write_text(
            build_week_rules_text(
                week_number=week_number,
                title=week_title,
                scope_items=scope_items,
                exclude_items=exclude_items,
                output_items=output_items,
                max_scope=max_scope,
            ),
            encoding="utf-8",
        )
        written.append(rules_path)

        assignment_dir = week_dir / "assignment"
        assignment_dir.mkdir(parents=True, exist_ok=True)
        assignment_path = assignment_dir / "assignment.md"
        assignment_path.write_text(
            build_assignment_text(
                week_number=week_number,
                objective=objective,
                tasks=tasks,
                submission=submission,
                max_tasks=max_tasks,
            ),
            encoding="utf-8",
        )
        written.append(assignment_path)
    return written


# ── CLI ──────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Populate course markdown templates deterministically.")
    parser.add_argument("--course-root", type=Path, help="Course directory under data/raw")
    parser.add_argument("--raw-root", type=Path, help="Raw markdown root for the same course")
    parser.add_argument("--cleaned-root", type=Path, help="Cleaned markdown root for the same course")
    parser.add_argument("--config", type=Path, help="Path to pipeline.yaml")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config(args.config)
    log = setup_logging("render_templates", cfg)

    course_id = cfg.get("course_id", "mkt4822-RL")
    course_root = (args.course_root or resolve_path(cfg["paths"]["data_raw"]) / course_id).resolve()
    raw_root = (args.raw_root or resolve_path(cfg["paths"]["output_raw_md"]) / course_id).resolve()
    cleaned_root = (args.cleaned_root or resolve_path(cfg["paths"]["output_cleaned_md"]) / course_id).resolve()

    try:
        syllabus_path = raw_root / "00_meta" / "MKT4822_syllabus.md"
        syllabus_text = read_text(syllabus_path)
        week_entries = parse_week_entries(syllabus_text)
        written: list[Path] = []
        written.extend(render_meta_templates(course_root, syllabus_text, week_entries))
        written.extend(render_week_templates(course_root, raw_root, cleaned_root, week_entries, cfg=cfg))
    except FileNotFoundError as exc:
        log.error("file not found: %s", exc)
        return 1
    except ValueError as exc:
        log.error("invalid input: %s", exc)
        return 1

    log.info("populated %d template file(s) under %s", len(written), course_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
