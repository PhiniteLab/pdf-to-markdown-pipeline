import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import type { SessionManager } from "./sessionManager";
import type { PathPolicy } from "./pathPolicy";

/**
 * Dashboard panel that displays pipeline metrics, quality badges,
 * entity statistics, and analysis summaries in a WebView sidebar.
 */
export class DashboardPanel implements vscode.WebviewViewProvider {
  static readonly viewId = "cortexmarkDashboard";

  private view?: vscode.WebviewView;

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly pathPolicy: PathPolicy,
    private readonly sessions: SessionManager,
  ) {}

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };
    this.refresh();
  }

  refresh(): void {
    if (!this.view) return;
    const metrics = this.gatherMetrics();
    this.view.webview.html = buildDashboardHtml(metrics);
  }

  // ── Metrics gathering ──────────────────────────────────────────────────

  private gatherMetrics(): DashboardMetrics {
    const activeSession = this.sessions.active();
    const sessionPaths = activeSession ? this.sessions.pathsFor(activeSession) : undefined;
    const metrics: DashboardMetrics = {
      sessionName: activeSession?.name,
      fileCount: 0,
      outputCount: 0,
      qa: undefined,
      entityStats: undefined,
      crossRefStats: undefined,
      algorithmStats: undefined,
      notationStats: undefined,
    };

    // Count input PDFs
    if (activeSession) {
      metrics.fileCount = activeSession.files.length;
    }

    // Count output MDs
    const cleanedDir = sessionPaths?.cleanedDir;
    if (cleanedDir && fs.existsSync(cleanedDir)) {
      metrics.outputCount = countFiles(cleanedDir, ".md");
    }

    // Load QA report summary
    metrics.qa = sessionPaths
      ? loadReportSummary<QASummary>(path.join(sessionPaths.qualityDir, "qa_report.json"), parseQASummary)
      : undefined;

    // Load cross-ref report
    metrics.crossRefStats = sessionPaths
      ? loadReportSummary<CrossRefStats>(path.join(sessionPaths.qualityDir, "crossref_report.json"), parseCrossRefStats)
      : undefined;

    // Load algorithm report
    metrics.algorithmStats = sessionPaths
      ? loadReportSummary<AlgorithmStats>(path.join(sessionPaths.qualityDir, "algorithm_report.json"), parseAlgorithmStats)
      : undefined;

    // Load notation report
    metrics.notationStats = sessionPaths
      ? loadReportSummary<NotationStats>(path.join(sessionPaths.qualityDir, "notation_report.json"), parseNotationStats)
      : undefined;

    return metrics;
  }
}

// ── Types ────────────────────────────────────────────────────────────────

interface DashboardMetrics {
  sessionName?: string;
  fileCount: number;
  outputCount: number;
  qa?: QASummary;
  entityStats?: EntityStats;
  crossRefStats?: CrossRefStats;
  algorithmStats?: AlgorithmStats;
  notationStats?: NotationStats;
}

interface QASummary {
  totalFiles: number;
  gold: number;
  silver: number;
  bronze: number;
  fail: number;
  avgScore: number;
}

interface EntityStats {
  theorems: number;
  proofs: number;
  definitions: number;
  algorithms: number;
  examples: number;
}

interface CrossRefStats {
  totalDefinitions: number;
  totalMentions: number;
  resolutionRate: number;
  unresolvedCount: number;
}

interface AlgorithmStats {
  totalAlgorithms: number;
  avgSteps: number;
  maxDepth: number;
}

interface NotationStats {
  uniqueSymbols: number;
  totalEntries: number;
  sourceCounts: Record<string, number>;
}

// ── Report loaders ─────────────────────────────────────────────────────────

function loadReportSummary<T>(filePath: string, parser: (data: unknown) => T | undefined): T | undefined {
  if (!fs.existsSync(filePath)) return undefined;
  try {
    const raw = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    return parser(raw);
  } catch {
    return undefined;
  }
}

function parseQASummary(data: unknown): QASummary | undefined {
  const d = data as Record<string, unknown>;
  const summary = (d.summary ?? d) as Record<string, unknown>;
  const files = (d.files ?? []) as Array<Record<string, unknown>>;
  const badges = files.map((f) => ((f.badge as string) ?? "").toUpperCase());
  const scores = files.map((f) => (f.score as number) ?? 0);
  if (files.length === 0) return undefined;
  return {
    totalFiles: files.length,
    gold: badges.filter((b) => b === "GOLD").length,
    silver: badges.filter((b) => b === "SILVER").length,
    bronze: badges.filter((b) => b === "BRONZE").length,
    fail: badges.filter((b) => b === "FAIL").length,
    avgScore: scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0,
  };
}

function parseCrossRefStats(data: unknown): CrossRefStats | undefined {
  const d = data as Record<string, unknown>;
  const summary = (d.summary ?? d) as Record<string, unknown>;
  return {
    totalDefinitions: (summary.total_definitions as number) ?? 0,
    totalMentions: (summary.total_mentions as number) ?? 0,
    resolutionRate: (summary.resolution_rate as number) ?? 0,
    unresolvedCount: (summary.unresolved as number) ?? 0,
  };
}

function parseAlgorithmStats(data: unknown): AlgorithmStats | undefined {
  const d = data as Record<string, unknown>;
  const summary = (d.summary ?? d) as Record<string, unknown>;
  return {
    totalAlgorithms: (summary.total_algorithms as number) ?? 0,
    avgSteps: (summary.avg_steps as number) ?? 0,
    maxDepth: (summary.max_depth as number) ?? 0,
  };
}

function parseNotationStats(data: unknown): NotationStats | undefined {
  const d = data as Record<string, unknown>;
  const summary = (d.summary ?? d) as Record<string, unknown>;
  return {
    uniqueSymbols: (summary.unique_symbols as number) ?? 0,
    totalEntries: (summary.total_entries as number) ?? 0,
    sourceCounts: (summary.source_counts as Record<string, number>) ?? {},
  };
}

// ── Utilities ──────────────────────────────────────────────────────────────

function countFiles(dir: string, ext: string): number {
  let count = 0;
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory()) {
        count += countFiles(path.join(dir, entry.name), ext);
      } else if (entry.name.endsWith(ext)) {
        count++;
      }
    }
  } catch {
    // Ignore read errors
  }
  return count;
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── HTML rendering ─────────────────────────────────────────────────────────

function buildDashboardHtml(m: DashboardMetrics): string {
  return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: var(--vscode-font-family);
  font-size: var(--vscode-font-size);
  color: var(--vscode-foreground);
  background: var(--vscode-sideBar-background);
  padding: 10px;
}
.section {
  margin-bottom: 14px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--vscode-textCodeBlock-background, rgba(127,127,127,.06));
}
.section-title {
  font-weight: 700;
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
  color: var(--vscode-descriptionForeground);
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 0;
  font-size: 0.9em;
}
.row .label { opacity: 0.85; }
.row .value { font-weight: 600; font-variant-numeric: tabular-nums; }
.badge-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.badge {
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 700;
  font-size: 0.8em;
  color: #000;
}
.badge.gold { background: #ffd700; }
.badge.silver { background: #c0c0c0; }
.badge.bronze { background: #cd7f32; }
.badge.fail { background: #ff4444; color: #fff; }
.progress-bar {
  width: 100%;
  height: 6px;
  background: var(--vscode-progressBar-background);
  border-radius: 3px;
  margin-top: 4px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}
.empty { opacity: 0.5; font-style: italic; font-size: 0.85em; }
</style>
</head>
<body>

<div class="section">
  <div class="section-title">\u{1F4CC} Active Session</div>
  <div class="row"><span class="label">Session</span><span class="value">${escapeHtml(m.sessionName ?? "none")}</span></div>
</div>

<div class="section">
  <div class="section-title">\u{1F4C4} Pipeline Overview</div>
  <div class="row"><span class="label">Input PDFs</span><span class="value">${m.fileCount}</span></div>
  <div class="row"><span class="label">Output files</span><span class="value">${m.outputCount}</span></div>
</div>

${renderQASection(m.qa)}
${renderCrossRefSection(m.crossRefStats)}
${renderAlgorithmSection(m.algorithmStats)}
${renderNotationSection(m.notationStats)}

</body>
</html>`;
}

function renderQASection(qa: QASummary | undefined): string {
  if (!qa) {
    return `<div class="section">
      <div class="section-title">\u{2705} Quality</div>
      <p class="empty">Run QA report to see metrics</p>
    </div>`;
  }

  const pctFill = Math.round(qa.avgScore * 100);
  const fillColor = pctFill >= 80 ? "#4caf50" : pctFill >= 60 ? "#ff9800" : "#f44336";

  return `<div class="section">
    <div class="section-title">\u{2705} Quality (${qa.totalFiles} files)</div>
    <div class="row"><span class="label">Average score</span><span class="value">${pctFill}%</span></div>
    <div class="progress-bar"><div class="progress-fill" style="width:${pctFill}%;background:${fillColor}"></div></div>
    <div class="badge-row">
      ${qa.gold > 0 ? `<span class="badge gold">\u{1F947} ${qa.gold} Gold</span>` : ""}
      ${qa.silver > 0 ? `<span class="badge silver">\u{1F948} ${qa.silver} Silver</span>` : ""}
      ${qa.bronze > 0 ? `<span class="badge bronze">\u{1F949} ${qa.bronze} Bronze</span>` : ""}
      ${qa.fail > 0 ? `<span class="badge fail">\u{274C} ${qa.fail} Fail</span>` : ""}
    </div>
  </div>`;
}

function renderCrossRefSection(stats: CrossRefStats | undefined): string {
  if (!stats) {
    return `<div class="section">
      <div class="section-title">\u{1F517} Cross References</div>
      <p class="empty">Run cross-ref analysis to see metrics</p>
    </div>`;
  }

  const pct = Math.round(stats.resolutionRate * 100);
  const fillColor = pct >= 90 ? "#4caf50" : pct >= 70 ? "#ff9800" : "#f44336";

  return `<div class="section">
    <div class="section-title">\u{1F517} Cross References</div>
    <div class="row"><span class="label">Definitions</span><span class="value">${stats.totalDefinitions}</span></div>
    <div class="row"><span class="label">Mentions</span><span class="value">${stats.totalMentions}</span></div>
    <div class="row"><span class="label">Resolution</span><span class="value">${pct}%</span></div>
    <div class="progress-bar"><div class="progress-fill" style="width:${pct}%;background:${fillColor}"></div></div>
    ${stats.unresolvedCount > 0 ? `<div class="row"><span class="label" style="color:#f44336">\u{26A0} Unresolved</span><span class="value">${stats.unresolvedCount}</span></div>` : ""}
  </div>`;
}

function renderAlgorithmSection(stats: AlgorithmStats | undefined): string {
  if (!stats) {
    return `<div class="section">
      <div class="section-title">\u{1F4BB} Algorithms</div>
      <p class="empty">Run algorithm extraction to see metrics</p>
    </div>`;
  }

  return `<div class="section">
    <div class="section-title">\u{1F4BB} Algorithms</div>
    <div class="row"><span class="label">Total</span><span class="value">${stats.totalAlgorithms}</span></div>
    <div class="row"><span class="label">Avg steps</span><span class="value">${stats.avgSteps.toFixed(1)}</span></div>
    <div class="row"><span class="label">Max depth</span><span class="value">${stats.maxDepth}</span></div>
  </div>`;
}

function renderNotationSection(stats: NotationStats | undefined): string {
  if (!stats) {
    return `<div class="section">
      <div class="section-title">\u{1D70B} Notation</div>
      <p class="empty">Run notation glossary to see metrics</p>
    </div>`;
  }

  const sourceRows = Object.entries(stats.sourceCounts)
    .map(([src, cnt]) => `<div class="row"><span class="label">${escapeHtml(src)}</span><span class="value">${cnt}</span></div>`)
    .join("\n");

  return `<div class="section">
    <div class="section-title">\u{1D70B} Notation</div>
    <div class="row"><span class="label">Unique symbols</span><span class="value">${stats.uniqueSymbols}</span></div>
    <div class="row"><span class="label">Total entries</span><span class="value">${stats.totalEntries}</span></div>
    ${sourceRows}
  </div>`;
}
