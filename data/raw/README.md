# data/raw — PDF Source Directory Structure

This directory organizes source PDF files by document type. Each subdirectory feeds into the same pipeline (convert → clean → chunk) and produces mirrored outputs under `outputs/`.

## Folder Taxonomy

| Folder | Description | Example Content |
|--------|-------------|-----------------|
| `manuscripts/` | Academic journal articles, conference papers | `ver1.pdf` (Kim & Yang, IEEE TAC 2023) |
| `books/` | Complete books (single PDF per book) | `sutton_barto_2018.pdf` |
| `textbooks/` | Textbooks — top-level PDFs or per-chapter splits | `reference_book.pdf` |
| `textbooks/chapters/` | Individual chapter PDFs from a textbook | `ch01_introduction.pdf` |
| `notes/` | Notes, handouts, reference packets | `topic03_overview.pdf` |
| `reports/` | Technical reports, white papers, surveys | `systems_report_2020.pdf` |
| `theses/` | Master's/PhD theses, dissertations | `dissertation_sample.pdf` |

## Usage

Process any folder through the pipeline:

```bash
# Process a specific document type
python -m cortexmark.convert --input data/raw/manuscripts --output-dir outputs/raw_md --no-manifest

# Or process a single file
python -m cortexmark.convert --input data/raw/books/my_book.pdf --output outputs/raw_md/books/my_book.md
```

## Output Mapping

```
data/raw/manuscripts/ver1.pdf
    → outputs/raw_md/manuscripts/ver1.md
    → outputs/cleaned_md/manuscripts/ver1.md
    → outputs/chunks/manuscripts/ver1/chunk_*.md
    → outputs/cleaned_md/manuscripts/ver1_metadata.md
    → outputs/cleaned_md/manuscripts/ver1_analysis.md
```

## Notes

- Each folder is processed independently — the pipeline uses `--input` to target any subdirectory.
- `.gitkeep` files are placed in empty directories to preserve structure in version control.
