import * as path from "path";
import * as vscode from "vscode";
import { ChatViewProvider } from "./chatView";
import { PipelineRunner } from "./pipelineRunner";
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

// ═══════════════════════════════════════════════════════════════════════════
// Activation
// ═══════════════════════════════════════════════════════════════════════════

export function activate(context: vscode.ExtensionContext): void {
  const wsRoot = root();
  if (!wsRoot) return;

  // ── Core services ──────────────────────────────────────────────────────
  const sessions = new SessionManager(wsRoot);
  const runner = new PipelineRunner();

  // ── Tree view ──────────────────────────────────────────────────────────
  const tree = new SessionTreeProvider(sessions);
  sessions.onDidChange(() => tree.refresh());

  // ── Chat webview ───────────────────────────────────────────────────────
  const chat = new ChatViewProvider(context.extensionUri, sessions, runner);

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

    chat.postMessage("system", `\uD83D\uDCE5 **${name}** detected \u2192 added to "${active.name}".`);

    if (cfg<boolean>("autoProcess")) {
      void processActiveSession(sessions, runner, chat, wsRoot);
    }
  });

  // ── Register everything ────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("pdfPipelinePanel", tree),
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewId, chat),
    watcher,
    sessions,
    runner,

    // Session commands
    vscode.commands.registerCommand("pdfPipeline.refresh", () => tree.refresh()),
    vscode.commands.registerCommand("pdfPipeline.newSession", () => cmdNewSession(sessions)),
    vscode.commands.registerCommand("pdfPipeline.deleteSession", (item?: PipelineItem) =>
      cmdDeleteSession(sessions, item),
    ),
    vscode.commands.registerCommand("pdfPipeline.setActiveSession", (item?: PipelineItem) =>
      cmdSetActive(sessions, item),
    ),
    vscode.commands.registerCommand("pdfPipeline.processSession", () =>
      processActiveSession(sessions, runner, chat, wsRoot),
    ),
    vscode.commands.registerCommand("pdfPipeline.addPdf", () => cmdAddPdf(sessions, wsRoot)),

    // Pipeline commands (use spawn runner)
    vscode.commands.registerCommand("pdfPipeline.runFull", () => cmdRunFull(runner, chat, wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.runConvert", () => cmdRunConvert(runner, wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.runQA", () => cmdRunQA(runner, wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.runDiff", () => cmdRunDiff(runner, wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.openConfig", () => cmdOpenConfig(wsRoot)),
    vscode.commands.registerCommand("pdfPipeline.openOutput", (arg?: string | PipelineItem) =>
      cmdOpenOutput(wsRoot, arg),
    ),
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

async function cmdDeleteSession(mgr: SessionManager, item?: PipelineItem): Promise<void> {
  const id = item?.sessionId;
  if (!id) return;
  const session = mgr.get(id);
  if (!session) return;
  const answer = await vscode.window.showWarningMessage(
    `Delete session "${session.name}"?`,
    { modal: true },
    "Delete",
  );
  if (answer === "Delete") {
    mgr.delete(id);
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
    filters: { "PDF Files": ["pdf"] },
    defaultUri: vscode.Uri.file(path.join(wsRoot, "data", "raw")),
    title: "Select PDFs to add",
  });
  if (!uris?.length) return;
  let count = 0;
  for (const uri of uris) {
    const rel = path.relative(wsRoot, uri.fsPath);
    const name = path.basename(uri.fsPath);
    if (mgr.addFile(active.id, name, rel)) {
      count++;
    }
  }
  if (count > 0) {
    void vscode.window.showInformationMessage(`Added ${count} PDF(s) to "${active.name}".`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Process active session (spawn-based)
// ═══════════════════════════════════════════════════════════════════════════

async function processActiveSession(
  mgr: SessionManager,
  runner: PipelineRunner,
  chat: ChatViewProvider,
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
  chat.postMessage("system", `\u23F3 Processing session "${session.name}"...`);

  const result = await runner.runPipeline(
    {
      python: cfg<string>("pythonPath"),
      root: wsRoot,
      config: cfg<string>("configPath"),
      engine: cfg<string>("defaultEngine"),
    },
    (line) => {
      // Forward progress lines to chat
      if (line.includes("Stage") || line.includes("stage") || line.includes("done") || line.includes("error")) {
        chat.postMessage("system", line);
      }
    },
  );

  if (result.exitCode === 0) {
    mgr.bulkUpdate(session.id, "processing", "done");
    chat.postMessage("system", `\u2705 Session "${session.name}" processed successfully.`);
    void vscode.window.showInformationMessage(`Pipeline complete for "${session.name}".`);
  } else {
    mgr.bulkUpdate(session.id, "processing", "error");
    chat.postMessage("system", `\u274C Pipeline failed (exit ${result.exitCode}).`);
    void vscode.window.showErrorMessage(`Pipeline failed. Check Output channel for details.`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Pipeline action commands (spawn-based)
// ═══════════════════════════════════════════════════════════════════════════

async function cmdRunFull(runner: PipelineRunner, chat: ChatViewProvider, wsRoot: string): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;
  chat.postMessage("system", "\uD83D\uDE80 Running full pipeline...");
  const result = await runner.runPipeline({
    python: cfg<string>("pythonPath"),
    root: wsRoot,
    config: cfg<string>("configPath"),
    engine: cfg<string>("defaultEngine"),
  });
  const msg = result.exitCode === 0 ? "\u2705 Full pipeline done." : `\u274C Pipeline failed (exit ${result.exitCode}).`;
  chat.postMessage("system", msg);
}

async function cmdRunConvert(runner: PipelineRunner, wsRoot: string): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;
  await runner.runPipeline({
    python: cfg<string>("pythonPath"),
    root: wsRoot,
    config: cfg<string>("configPath"),
    engine: cfg<string>("defaultEngine"),
    stages: ["convert"],
  });
}

async function cmdRunQA(runner: PipelineRunner, wsRoot: string): Promise<void> {
  if (!need(wsRoot) || runner.busy) return;
  await runner.runQA({
    python: cfg<string>("pythonPath"),
    root: wsRoot,
    config: cfg<string>("configPath"),
    input: path.resolve(wsRoot, "outputs/cleaned_md"),
    output: path.resolve(wsRoot, "outputs/quality/qa_report.json"),
  });
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
    python: cfg<string>("pythonPath"),
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


