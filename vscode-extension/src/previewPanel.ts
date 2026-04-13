import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

/**
 * Markdown preview panel that renders converted output files
 * with QA badges, entity highlights, and formula rendering.
 */
export class PreviewPanel implements vscode.Disposable {
  static readonly viewType = "pdfPipeline.preview";

  private panel: vscode.WebviewPanel | undefined;
  private currentFile: string | undefined;
  private readonly disposables: vscode.Disposable[] = [];

  constructor(private readonly extensionUri: vscode.Uri) {}

  /**
   * Open or reveal the preview for a given Markdown file.
   */
  show(filePath: string): void {
    const column = vscode.ViewColumn.Beside;

    if (this.panel) {
      this.panel.reveal(column);
    } else {
      this.panel = vscode.window.createWebviewPanel(
        PreviewPanel.viewType,
        "Markdown Preview",
        column,
        {
          enableScripts: true,
          localResourceRoots: [this.extensionUri],
          retainContextWhenHidden: true,
        },
      );

      this.panel.onDidDispose(() => {
        this.panel = undefined;
        this.currentFile = undefined;
      }, null, this.disposables);
    }

    this.currentFile = filePath;
    this.update(filePath);
  }

  /**
   * Refresh the currently displayed file.
   */
  refresh(): void {
    if (this.currentFile) {
      this.update(this.currentFile);
    }
  }

  private update(filePath: string): void {
    if (!this.panel) return;

    const fileName = path.basename(filePath);
    this.panel.title = `Preview: ${fileName}`;

    let content = "";
    let qaData: QAInfo | undefined;

    // Read the markdown file
    if (fs.existsSync(filePath)) {
      content = fs.readFileSync(filePath, "utf-8");
    } else {
      content = `*File not found: ${fileName}*`;
    }

    // Try to load QA data for this file
    const wsRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (wsRoot) {
      qaData = loadQAInfo(filePath, wsRoot);
    }

    this.panel.webview.html = buildPreviewHtml(content, qaData, fileName);
  }

  dispose(): void {
    this.panel?.dispose();
    for (const d of this.disposables) {
      d.dispose();
    }
  }
}

// ── QA info types ──────────────────────────────────────────────────────────

interface QAInfo {
  badge: string;
  score: number;
  issues: string[];
}

// ── Load QA report data ────────────────────────────────────────────────────

function loadQAInfo(filePath: string, wsRoot: string): QAInfo | undefined {
  const qaPath = path.join(wsRoot, "outputs", "quality", "qa_report.json");
  if (!fs.existsSync(qaPath)) return undefined;

  try {
    const raw = fs.readFileSync(qaPath, "utf-8");
    const report = JSON.parse(raw) as {
      files?: Array<{
        file: string;
        badge?: string;
        score?: number;
        issues?: Array<{ message: string }>;
      }>;
    };

    const basename = path.basename(filePath, ".md");
    const entry = report.files?.find(
      (f) => f.file.includes(basename),
    );

    if (!entry) return undefined;
    return {
      badge: entry.badge ?? "?",
      score: entry.score ?? 0,
      issues: entry.issues?.map((i) => i.message) ?? [],
    };
  } catch {
    return undefined;
  }
}

// ── Build HTML ─────────────────────────────────────────────────────────────

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdownToHtml(md: string): string {
  // Lightweight Markdown→HTML for preview (headings, bold, italic, code, lists, tables)
  let html = escapeHtml(md);

  // Code blocks (fenced)
  html = html.replace(
    /```(\w*)\n([\s\S]*?)```/g,
    (_m, lang, code) => `<pre><code class="language-${lang}">${code}</code></pre>`,
  );

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Display math $$...$$
  html = html.replace(
    /\$\$([\s\S]*?)\$\$/g,
    (_m, eq) => `<div class="math-block">$$${eq}$$</div>`,
  );

  // Inline math $...$
  html = html.replace(
    /\$([^$\n]+?)\$/g,
    (_m, eq) => `<span class="math-inline">$${eq}$</span>`,
  );

  // Headings
  html = html.replace(/^#{6}\s+(.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^#{5}\s+(.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^#{4}\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^#{3}\s+(.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^#{2}\s+(.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^#{1}\s+(.+)$/gm, "<h1>$1</h1>");

  // Bold / italic
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Horizontal rule
  html = html.replace(/^---+$/gm, "<hr>");

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");

  // Tables (basic pipe-delimited)
  html = html.replace(/^\|(.+)\|$/gm, (_m, row: string) => {
    const cells = row.split("|").map((c: string) => `<td>${c.trim()}</td>`).join("");
    return `<tr>${cells}</tr>`;
  });
  // Wrap consecutive <tr> in <table>
  html = html.replace(/((?:<tr>.*<\/tr>\n?)+)/g, "<table>$1</table>");
  // Remove separator rows (---+|---+)
  html = html.replace(/<tr><td>[-:]+<\/td>(?:<td>[-:]+<\/td>)*<\/tr>/g, "");

  // Paragraphs: wrap remaining plain text blocks
  html = html.replace(/^(?!<[a-z])((?!<).+)$/gm, "<p>$1</p>");

  // Clean up consecutive list items into <ul>
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  return html;
}

function badgeColor(badge: string): string {
  const map: Record<string, string> = {
    GOLD: "#ffd700",
    SILVER: "#c0c0c0",
    BRONZE: "#cd7f32",
    FAIL: "#ff4444",
  };
  return map[badge.toUpperCase()] ?? "#888";
}

function buildPreviewHtml(content: string, qa: QAInfo | undefined, fileName: string): string {
  const renderedContent = renderMarkdownToHtml(content);

  const qaBadge = qa
    ? `<span class="badge" style="background:${badgeColor(qa.badge)}">${escapeHtml(qa.badge)}</span>
       <span class="score">${(qa.score * 100).toFixed(0)}%</span>`
    : "";

  const qaIssues = qa?.issues.length
    ? `<details class="qa-issues"><summary>${qa.issues.length} issue(s)</summary>
       <ul>${qa.issues.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul></details>`
    : "";

  // Count entities in content
  const stats = extractStats(content);

  return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: var(--vscode-editor-font-family, 'Segoe UI', sans-serif);
  font-size: var(--vscode-editor-font-size, 14px);
  color: var(--vscode-editor-foreground);
  background: var(--vscode-editor-background);
  padding: 0;
}
.toolbar {
  position: sticky; top: 0; z-index: 10;
  display: flex; align-items: center; gap: 8px;
  padding: 8px 16px;
  background: var(--vscode-editorWidget-background);
  border-bottom: 1px solid var(--vscode-editorWidget-border);
  flex-wrap: wrap;
}
.toolbar .filename {
  font-weight: 600;
  font-size: 1.05em;
  margin-right: auto;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 0.85em;
  color: #000;
}
.score { font-size: 0.9em; opacity: 0.8; }
.stat {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 0.8em;
  background: var(--vscode-badge-background);
  color: var(--vscode-badge-foreground);
}
.content {
  padding: 16px 24px;
  max-width: 860px;
  margin: 0 auto;
  line-height: 1.6;
}
h1, h2, h3, h4, h5, h6 {
  margin: 1.2em 0 0.4em;
  color: var(--vscode-editor-foreground);
}
h1 { font-size: 1.8em; border-bottom: 1px solid var(--vscode-editorWidget-border); padding-bottom: 4px; }
h2 { font-size: 1.5em; }
h3 { font-size: 1.25em; }
p { margin: 0.5em 0; }
code {
  background: var(--vscode-textCodeBlock-background);
  padding: 1px 4px;
  border-radius: 3px;
  font-family: var(--vscode-editor-font-family);
  font-size: 0.9em;
}
pre {
  background: var(--vscode-textCodeBlock-background);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.8em 0;
}
pre code { background: none; padding: 0; }
table {
  border-collapse: collapse;
  margin: 0.8em 0;
  width: 100%;
}
td, th {
  border: 1px solid var(--vscode-editorWidget-border);
  padding: 6px 10px;
  text-align: left;
}
ul { margin: 0.5em 0 0.5em 1.5em; }
li { margin: 0.2em 0; }
hr { margin: 1em 0; border: none; border-top: 1px solid var(--vscode-editorWidget-border); }
strong { color: var(--vscode-textLink-foreground); }
.math-block {
  display: block;
  text-align: center;
  margin: 0.8em 0;
  padding: 8px;
  background: var(--vscode-textCodeBlock-background);
  border-radius: 4px;
  font-family: var(--vscode-editor-font-family);
  overflow-x: auto;
}
.math-inline {
  font-family: var(--vscode-editor-font-family);
  padding: 0 2px;
}
.qa-issues {
  margin-top: 6px;
  padding: 6px 12px;
  background: var(--vscode-textCodeBlock-background);
  border-radius: 4px;
  font-size: 0.85em;
}
.qa-issues summary { cursor: pointer; font-weight: 600; }
.qa-issues ul { margin: 6px 0 0 16px; }
blockquote {
  border-left: 3px solid var(--vscode-textLink-foreground);
  margin: 0.5em 0;
  padding: 4px 12px;
  opacity: 0.85;
}
</style>
</head>
<body>
<div class="toolbar">
  <span class="filename">${escapeHtml(fileName)}</span>
  ${qaBadge}
  ${stats.theorems > 0 ? `<span class="stat">\u{1D4E3} ${stats.theorems} theorem(s)</span>` : ""}
  ${stats.proofs > 0 ? `<span class="stat">\u{1D4AB} ${stats.proofs} proof(s)</span>` : ""}
  ${stats.definitions > 0 ? `<span class="stat">\u{1D4D3} ${stats.definitions} def(s)</span>` : ""}
  ${stats.algorithms > 0 ? `<span class="stat">\u{1D4D0} ${stats.algorithms} algo(s)</span>` : ""}
  ${stats.formulas > 0 ? `<span class="stat">\u{03A3} ${stats.formulas} formula(s)</span>` : ""}
  ${stats.figures > 0 ? `<span class="stat">\u{1F4CA} ${stats.figures} figure(s)</span>` : ""}
</div>
${qaIssues}
<div class="content">
${renderedContent}
</div>
</body>
</html>`;
}

// ── Content statistics ─────────────────────────────────────────────────────

interface ContentStats {
  theorems: number;
  proofs: number;
  definitions: number;
  algorithms: number;
  formulas: number;
  figures: number;
}

function extractStats(content: string): ContentStats {
  return {
    theorems: countPattern(content, /\b(?:Theorem|Lemma|Proposition|Corollary)\b/gi),
    proofs: countPattern(content, /\bProof[.:]/gi),
    definitions: countPattern(content, /\bDefinition\b/gi),
    algorithms: countPattern(content, /\bAlgorithm\s+\d/gi),
    formulas: countPattern(content, /\$\$[\s\S]*?\$\$/g),
    figures: countPattern(content, /!\[/g),
  };
}

function countPattern(text: string, pattern: RegExp): number {
  return (text.match(pattern) ?? []).length;
}
