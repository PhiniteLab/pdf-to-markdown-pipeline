import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { ChatViewProvider } from "./chatView";
import { DashboardPanel } from "./dashboardPanel";
import { PipelineRunner } from "./pipelineRunner";
import { PreviewPanel } from "./previewPanel";
import { SessionManager } from "./sessionManager";
import { PipelineItem, SessionTreeProvider } from "./sessionTree";

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

function root(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function cfg<T>(key: string): T {
  return vscode.workspace.getConfiguration("pdfPipeline").get<T>(key) as T;
}

function need(r: string | undefined): r is string {
  if (!r) {
    void vscode.window.showErrorMessage("Open a workspace folder first.");
  }
  return !!r;
}

/** Derive the input directory from the active session's files. */
function sessionInputDir(mgr: SessionManager, wsRoot: string): string | undefined {
  const session = mgr.active();
  if (!session || session.files.length === 0) return undefined;
  const first = session.files[0];
  const abs = path.resolve(wsRoot, first.relativePath);
  return path.dirname(abs);
}

/** Resolve the Python executable: check venv first, then user setting. */
function resolvePython(wsRoot: string): string {
  const userPython = cfg<string>("pythonPath");
  // If user explicitly set an absolute path, honour it.
  if (userPython && path.isAbsolute(userPython)) {
    return userPython;
  }
  // Auto-detect workspace venv
  const candidates = [
    path.join(wsRoot, ".venv", "bin", "python"),
    path.join(wsRoot, ".venv", "bin", "python3"),
    path.join(wsRoot, "venv", "bin", "python"),
    path.join(wsRoot, "venv", "bin", "python3"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      return c;
    }
  }
  // Fallback to user setting or python3
  return userPython || "python3";
}

// ═══════════════════════════════════════════════════════════════════════════
// Activation
// ═══════════════════════════════════════════════════════════════════════════

export function activate(context: vscode.ExtensionContext): void {
  const wsRoot = root();
  if (!wsRoot) return;

  // ── Core services ──────────────────────────────────────────────────────
  const sessions = new SessionManager(wsRoot);
  const runner = new PipelineRunner();
  const preview = new PreviewPanel(context.extensionUri);
  const dashboard = new DashboardPanel(context.extensionUri, wsRoot);
  const chat = new ChatViewProvider(context.extensionUri);

  // ── Tree view ──────────────────────────────────────────────────────────
  const tree = new SessionTreeProvider(sessions, wsRoot);
  sessions.onDidChange(() => tree.refresh());

  // ── File watcher — auto-detect PDFs ────────────────────────────────────
  const watcher = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(wsRoot, "data/raw/**/*.pdf"),
  );
  watcher.onDidCreate((uri) => {
    const active = sessions.active();
    if (!active) return;
    const relPath = path.relative(wsRoot, uri.fsPath);
    const name = path.basename(uri.fsPath);
    const added = sessions.addFile(active.id, name, relPath);
    if (!added) return;

    if (cfg<boolean>("autoProcess")) {
      void processActiveSession(sessions, runner, wsRoot);
    }
  });

  // ── Output watcher — auto-refresh tree on output changes ─────────────
  const outWatcher = vscode.workspace.createFileSystemWatcher(
    new vscode.RelativePattern(wsRoot, "outputs/**"),
  );
  outWatcher.onDidCreate(() => tree.refresh());
  outWatcher.onDidDelete(() => tree.refresh());

  // ── Register everything ────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("pdfPipelinePanel", tree),
    vscode.window.registerWebviewViewProvider(DashboardPanel.viewId, dashboard),
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, chat),
    watcher,
    outWatcher,
    sessions,
    runner,
    preview,

    // Session commands
    vscode.commands.registerCommand("pdfPipeline.refresh", () => {
      tree.refresh();
      dashboard.refresh();
    }),
    vscode.commands.registerCommand("pdfPipeline.newSession", () => cmdNewSession(sessions)),
    vscode.commands.registerCommand("pdfPipeline.deleteSession", (item?: PipelineItem) =>
      cmdDeleteSession(sessions, wsRoot, item),
    ),
    vscode.commands.registerCommand("pdfPipeline.setActiveSession", (item?: PipelineItem) =>
      cmdSetActive(sessions, item),
    ),
    vscode.commands.registerCommand("pdfPipeline.processSession", () =>
      processActiveSession(sessions, runner, wsRoot),
    ),
    vscode.commands.registerCommand("pdfPipeline.addPdf", () => cmdAddPdf(sessions, wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.addFolder", () => cmdAddFolder(sessions, wsRoot)),

    // Pipeline commands (use spawn runner)
    vscode.commands.registerCommand("pdfPipeline.runFull", () => cmdRunFull(runner, wsRoot, sessions)),
    vscode.commands.registerCommand("pdfPipeline.runConvert", () => cmdRunConvert(runner, wsRoot, sessions)),
    vscode.commands.registerCommand("pdfPipeline.runQA", () => cmdRunQA(runner, wsRoot, dashboard)),
    vscode.commands.registerCommand("pdfPipeline.runDiff", () => cmdRunDiff(runner, wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.openConfig", () => cmdOpenConfig(wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.openOutput", (arg?: string | PipelineItem) =>
      cmdOpenOutput(wsRoot, arg),
    ),
    vscode.commands.registerCommand("pdfPipeline.deleteOutput", (item?: PipelineItem) =>
      cmdDeleteOutput(item, tree),
    ),

    // Analysis commands
    vscode.commands.registerCommand("pdfPipeline.runCrossRef", () =>
      cmdRunAnalysis(runner, wsRoot, "crossRef", dashboard),
    ),
    vscode.commands.registerCommand("pdfPipeline.runAlgorithm", () =>
      cmdRunAnalysis(runner, wsRoot, "algorithm", dashboard),
    ),
    vscode.commands.registerCommand("pdfPipeline.runNotation", () =>
      cmdRunAnalysis(runner, wsRoot, "notation", dashboard),
    ),
    vscode.commands.registerCommand("pdfPipeline.runSemanticChunk", () =>
      cmdRunAnalysis(runner, wsRoot, "semanticChunk", dashboard),
    ),
    vscode.commands.registerCommand("pdfPipeline.runAllAnalysis", () =>
      cmdRunAllAnalysis(runner, wsRoot, dashboard),
    ),

    // Preview commands
    vscode.commands.registerCommand("pdfPipeline.previewFile", (arg?: string | PipelineItem) =>
      cmdPreview(preview, wsRoot, arg),
    ),
    vscode.commands.registerCommand("pdfPipeline.refreshPreview", () => preview.refresh()),
    vscode.commands.registerCommand("pdfPipeline.refreshDashboard", () => dashboard.refresh()),
  );
}

export function deactivate(): void {
  // no-op — disposables handled by subscriptions
}

// ═══════════════════════════════════════════════════════════════════════════
// Session commands
// ═══════════════════════════════════════════════════════════════════════════

async function cmdNewSession(mgr: SessionManager): Promise<void> {
  const name = await vscode.window.showInputBox({
    title: "New Session",
    prompt: "Enter a name for the session",
    placeHolder: "e.g. RL Papers",
  });
  if (!name) return;
  const s = mgr.create(name);
  void vscode.window.showInformationMessage(`Session "${s.name}" created and set as active.`);
}

async function cmdDeleteSession(mgr: SessionManager, wsRoot: string, item?: PipelineItem): Promise<void> {
  const id = item?.sessionId;
  if (!id) return;
  const session = mgr.get(id);
  if (!session) return;
  const answer = await vscode.window.showWarningMessage(
    `Delete session "${session.name}" and its outputs?`,
    { modal: true },
    "Delete",
  );
  if (answer === "Delete") {
    cleanSessionOutputs(session, wsRoot);
    mgr.delete(id);
  }
}

/** Remove output files generated from the session's PDFs. */
function cleanSessionOutputs(session: { name: string; files: { relativePath: string }[] }, wsRoot: string): void {
  const outputDirs = ["outputs/raw_md", "outputs/cleaned_md", "outputs/chunks"];

  // Remove session-scoped output directories
  for (const outDir of outputDirs) {
    const sessionDir = path.join(wsRoot, outDir, session.name);
    if (fs.existsSync(sessionDir)) {
      fs.rmSync(sessionDir, { recursive: true, force: true });
    }
  }

  // Remove session-specific manifest
  const sessionManifest = path.join(wsRoot, "outputs", `.manifest-${session.name}.json`);
  if (fs.existsSync(sessionManifest)) {
    fs.rmSync(sessionManifest, { force: true });
  }
}

function cmdSetActive(mgr: SessionManager, item?: PipelineItem): void {
  const id = item?.sessionId;
  if (id) {
    mgr.setActive(id);
  }
}

async function cmdAddPdf(mgr: SessionManager, wsRoot: string): Promise<void> {
  const active = mgr.active();
  if (!active) {
    void vscode.window.showWarningMessage("Create a session first.");
    return;
  }
  const uris = await vscode.window.showOpenDialog({
    canSelectMany: true,
    canSelectFiles: true,
    canSelectFolders: false,
    filters: { "PDF Files": ["pdf"] },
    defaultUri: vscode.Uri.file(path.join(wsRoot, "data", "raw")),
    title: "Select PDF files to add",
  });
  if (!uris?.length) return;
  const count = addPdfUris(mgr, active.id, uris, wsRoot);
  if (count > 0) {
    void vscode.window.showInformationMessage(`Added ${count} PDF(s) to "${active.name}".`);
  }
}

async function cmdAddFolder(mgr: SessionManager, wsRoot: string): Promise<void> {
  const active = mgr.active();
  if (!active) {
    void vscode.window.showWarningMessage("Create a session first.");
    return;
  }
  const uris = await vscode.window.showOpenDialog({
    canSelectMany: false,
    canSelectFiles: false,
    canSelectFolders: true,
    defaultUri: vscode.Uri.file(path.join(wsRoot, "data", "raw")),
    title: "Select a folder containing PDFs",
  });
  if (!uris?.length) return;
  const folderUri = uris[0];
  const pattern = new vscode.RelativePattern(folderUri, "**/*.pdf");
  const pdfUris = await vscode.workspace.findFiles(pattern);
  if (pdfUris.length === 0) {
    void vscode.window.showWarningMessage("No PDF files found in the selected folder.");
    return;
  }
  const count = addPdfUris(mgr, active.id, pdfUris, wsRoot);
  if (count > 0) {
    void vscode.window.showInformationMessage(`Added ${count} PDF(s) from folder to "${active.name}".`);
  }
}

function addPdfUris(mgr: SessionManager, sessionId: string, uris: readonly vscode.Uri[], wsRoot: string): number {
  let count = 0;
  for (const uri of uris) {
    const rel = path.relative(wsRoot, uri.fsPath);
    const name = path.basename(uri.fsPath);
    if (mgr.addFile(sessionId, name, rel)) {
      count++;
    }
  }
  return count;
}

// ═══════════════════════════════════════════════════════════════════════════
// Process active session (spawn-based)
// ═══════════════════════════════════════════════════════════════════════════

async function processActiveSession(
  mgr: SessionManager,
  runner: PipelineRunner,
  wsRoot: string,
): Promise<void> {
  if (!need(wsRoot)) return;
  const session = mgr.active();
  if (!session) {
    void vscode.window.showWarningMessage("No active session.");
    return;
  }
  if (runner.busy) {
    void vscode.window.showWarningMessage("Pipeline is already running.");
    return;
  }

  // Mark queued files as processing
  mgr.bulkUpdate(session.id, "queued", "processing");

  const inputDir = sessionInputDir(mgr, wsRoot);
  const result = await runner.runPipeline(
    {
      python: resolvePython(wsRoot),
      root: wsRoot,
      config: cfg<string>("configPath"),
      engine: cfg<string>("defaultEngine"),
      input: inputDir,
      sessionName: session.name,
    },
  );

  if (result.exitCode === 0) {
    mgr.bulkUpdate(session.id, "processing", "done");
    void vscode.window.showInformationMessage(`Pipeline complete for "${session.name}".`);
  } else {
    mgr.bulkUpdate(session.id, "processing", "error");
    void vscode.window.showErrorMessage(`Pipeline failed. Check Output channel for details.`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Pipeline action commands (spawn-based)
// ═══════════════════════════════════════════════════════════════════════════

async function cmdRunFull(runner: PipelineRunner, wsRoot: string, mgr: SessionManager): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;
  const session = mgr.active();
  await runner.runPipeline({
    python: resolvePython(wsRoot),
    root: wsRoot,
    config: cfg<string>("configPath"),
    engine: cfg<string>("defaultEngine"),
    input: sessionInputDir(mgr, wsRoot),
    sessionName: session?.name,
  });
}

async function cmdRunConvert(runner: PipelineRunner, wsRoot: string, mgr: SessionManager): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;
  const session = mgr.active();
  await runner.runPipeline({
    python: resolvePython(wsRoot),
    root: wsRoot,
    config: cfg<string>("configPath"),
    engine: cfg<string>("defaultEngine"),
    stages: ["convert"],
    input: sessionInputDir(mgr, wsRoot),
    sessionName: session?.name,
  });
}

async function cmdRunQA(runner: PipelineRunner, wsRoot: string, dashboard: DashboardPanel): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;
  await runner.runQA({
    python: resolvePython(wsRoot),
    root: wsRoot,
    config: cfg<string>("configPath"),
    input: path.resolve(wsRoot, "outputs/cleaned_md"),
    output: path.resolve(wsRoot, "outputs/quality/qa_report.json"),
  });
  dashboard.refresh();
}

async function cmdRunDiff(runner: PipelineRunner, wsRoot: string): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;

  const oldDir = await vscode.window.showInputBox({
    title: "Old folder",
    prompt: "Path to old output folder",
    value: path.resolve(wsRoot, "outputs/cleaned_md"),
  });
  if (!oldDir) return;
  const newDir = await vscode.window.showInputBox({
    title: "New folder",
    prompt: "Path to new output folder",
    value: path.resolve(wsRoot, "outputs/raw_md"),
  });
  if (!newDir) return;

  await runner.runDiff({
    python: resolvePython(wsRoot),
    root: wsRoot,
    config: cfg<string>("configPath"),
    oldDir,
    newDir,
    output: path.resolve(wsRoot, "outputs/quality/diff_report.json"),
  });
}

async function cmdOpenConfig(wsRoot: string): Promise<void> {
  if (!need(wsRoot)) return;
  const p = path.resolve(wsRoot, cfg<string>("configPath"));
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(p));
  await vscode.window.showTextDocument(doc, { preview: false });
}

async function cmdOpenOutput(wsRoot: string, arg?: string | PipelineItem): Promise<void> {
  if (!need(wsRoot)) return;
  let rel: string | undefined;
  if (typeof arg === "string") {
    rel = arg;
  } else if (arg instanceof PipelineItem && arg.command?.arguments?.[0]) {
    rel = arg.command.arguments[0] as string;
  }
  if (!rel) return;
  await vscode.commands.executeCommand("revealInExplorer", vscode.Uri.file(path.resolve(wsRoot, rel)));
}

async function cmdDeleteOutput(item: PipelineItem | undefined, tree: SessionTreeProvider): Promise<void> {
  if (!item?.fsPath) return;
  const name = path.basename(item.fsPath);
  const isDir = fs.existsSync(item.fsPath) && fs.statSync(item.fsPath).isDirectory();
  const answer = await vscode.window.showWarningMessage(
    `Delete ${isDir ? "folder" : "file"} "${name}"?`,
    { modal: true },
    "Delete",
  );
  if (answer !== "Delete") return;
  fs.rmSync(item.fsPath, { recursive: true, force: true });
  tree.refresh();
}

// ═══════════════════════════════════════════════════════════════════════════
// Analysis commands
// ═══════════════════════════════════════════════════════════════════════════

type AnalysisKind = "crossRef" | "algorithm" | "notation" | "semanticChunk";

async function cmdRunAnalysis(
  runner: PipelineRunner,
  wsRoot: string,
  kind: AnalysisKind,
  dashboard: DashboardPanel,
): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;

  const inputDir = path.resolve(wsRoot, "outputs/cleaned_md");
  if (!fs.existsSync(inputDir)) {
    void vscode.window.showWarningMessage("No cleaned Markdown output found. Run the pipeline first.");
    return;
  }

  const python = resolvePython(wsRoot);
  const opts = { python, root: wsRoot, input: inputDir };

  let result;
  switch (kind) {
    case "crossRef":
      result = await runner.runCrossRef(opts);
      break;
    case "algorithm":
      result = await runner.runAlgorithmExtract(opts);
      break;
    case "notation":
      result = await runner.runNotationGlossary(opts);
      break;
    case "semanticChunk":
      result = await runner.runSemanticChunk(opts);
      break;
  }

  if (result.exitCode === 0) {
    void vscode.window.showInformationMessage(`${kind} analysis complete.`);
  } else {
    void vscode.window.showErrorMessage(`${kind} analysis failed. Check Output for details.`);
  }

  dashboard.refresh();
}

async function cmdRunAllAnalysis(
  runner: PipelineRunner,
  wsRoot: string,
  dashboard: DashboardPanel,
): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;

  const inputDir = path.resolve(wsRoot, "outputs/cleaned_md");
  if (!fs.existsSync(inputDir)) {
    void vscode.window.showWarningMessage("No cleaned Markdown output found. Run the pipeline first.");
    return;
  }

  const python = resolvePython(wsRoot);
  const opts = { python, root: wsRoot, input: inputDir };

  const analyses: [string, () => Promise<import("./pipelineRunner").RunResult>][] = [
    ["Cross References", () => runner.runCrossRef(opts)],
    ["Algorithm Extraction", () => runner.runAlgorithmExtract(opts)],
    ["Notation Glossary", () => runner.runNotationGlossary(opts)],
    ["Semantic Chunking", () => runner.runSemanticChunk(opts)],
  ];

  let failed = 0;
  for (const [label, run] of analyses) {
    const res = await run();
    if (res.exitCode !== 0) {
      void vscode.window.showWarningMessage(`${label} failed.`);
      failed++;
    }
  }

  dashboard.refresh();

  if (failed === 0) {
    void vscode.window.showInformationMessage("All analyses complete.");
  } else {
    void vscode.window.showWarningMessage(`${failed} analysis module(s) failed.`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Preview command
// ═══════════════════════════════════════════════════════════════════════════

function cmdPreview(preview: PreviewPanel, wsRoot: string, arg?: string | PipelineItem): void {
  if (!need(wsRoot)) return;

  let filePath: string | undefined;

  if (typeof arg === "string") {
    filePath = path.isAbsolute(arg) ? arg : path.resolve(wsRoot, arg);
  } else if (arg instanceof PipelineItem && arg.fsPath) {
    filePath = arg.fsPath;
  }

  if (!filePath) {
    // Try to preview the active editor's file
    const editor = vscode.window.activeTextEditor;
    if (editor && editor.document.languageId === "markdown") {
      filePath = editor.document.uri.fsPath;
    }
  }

  if (!filePath) {
    void vscode.window.showWarningMessage("No Markdown file to preview. Select a file or open one in the editor.");
    return;
  }

  preview.show(filePath);
}


