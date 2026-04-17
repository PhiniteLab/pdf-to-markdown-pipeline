import * as cp from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import { ChatViewProvider } from "./chatView";
import { DashboardPanel } from "./dashboardPanel";
import { PipelineRunner } from "./pipelineRunner";
import { PreviewPanel } from "./previewPanel";
import { SessionManager } from "./sessionManager";
import { PipelineItem, SessionTreeProvider } from "./sessionTree";
import type { Session } from "./types";
import {
  getExplicitStringSetting,
  resolveExecutableOverride,
  resolvePathPolicy,
  resolveWorkspaceEnvValue,
  resolveWorkspaceProcessEnv,
  type PathPolicy,
} from "./pathPolicy";
import { assertWithinRoot } from "./sessionLayout";

// ═══════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════

interface DoctorCheck {
  title: string;
  status: "ok" | "warn" | "error";
  details: string;
  fixes?: string[];
}

interface EnvironmentDoctorReport {
  generatedAt: string;
  workspace: string;
  python: string;
  pythonRunnable: boolean;
  pythonVersion: string;
  defaultEngine: string;
  pathPolicy: {
    configPath: string;
    configFound: boolean;
    configNotes: string[];
    dataRoot: string;
    sessionsRoot: string;
    outputRoots: PathPolicy["outputRoots"];
    sessionStorePath: string;
  };
  checks: DoctorCheck[];
  healthy: boolean;
  errors: number;
  warnings: number;
}

const DOCS_URL = "https://github.com/PhiniteLab/pdf-to-markdown-pipeline/blob/main/docs/vscode/setup.md";
const STARTUP_DOCTOR_KEY_PREFIX = "cortexmark.startupDoctorLastChecked";
const PYTHON_MIN_MINOR = 11;
const MIN_PYTHON_VERSION = `3.${PYTHON_MIN_MINOR}`;
const DOCTOR_CHANNEL_NAME = "CortexMark Environment";
const PYTHON_PATH_ENV_KEYS = ["CORTEXMARK_PYTHON_PATH", "CORTEXMARK_PYTHON", "PIPELINE_PYTHON"];
const doctorChannel: vscode.OutputChannel = vscode.window.createOutputChannel(DOCTOR_CHANNEL_NAME);

function root(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

function cfg<T>(key: string): T {
  return vscode.workspace.getConfiguration("cortexmark").get<T>(key) as T;
}

function need(r: string | undefined): r is string {
  if (!r) {
    void vscode.window.showErrorMessage("Open a workspace folder first.");
  }
  return !!r;
}

async function runPythonCheck(
  python: string,
  code: string,
  env: NodeJS.ProcessEnv,
  timeoutMs = 12_000,
): Promise<{ ok: boolean; stdout: string; stderr: string }> {
  return await new Promise((resolve) => {
    cp.execFile(
      python,
      ["-c", code],
      { timeout: timeoutMs, env },
      (err, stdout, stderr) => {
        resolve({
          ok: !err,
          stdout: String(stdout || "").trim(),
          stderr: String(stderr || "").trim(),
        });
      },
    );
  });
}

function pushCheck(
  report: DoctorCheck[],
  status: DoctorCheck["status"],
  title: string,
  details: string,
  fixes?: string[],
): void {
  report.push({ title, status, details, fixes: fixes?.filter(Boolean) });
}

function pythonVersionParts(result: string): { major: number; minor: number } | undefined {
  const match = result.match(/^(\d+)\.(\d+)/);
  if (!match) return undefined;
  const major = Number.parseInt(match[1], 10);
  const minor = Number.parseInt(match[2], 10);
  if (!Number.isFinite(major) || !Number.isFinite(minor)) return undefined;
  return { major, minor };
}

function pythonExecutableLabel(raw: string): string {
  return raw.includes(" ") ? `"${raw}"` : raw;
}

async function runEnvironmentDoctor(policy: PathPolicy): Promise<EnvironmentDoctorReport> {
  const reportChecks: DoctorCheck[] = [];
  const now = new Date().toLocaleString();
  const engine = (cfg<string>("defaultEngine") || "dual") as string;
  const python = await resolvePython(policy.workspaceRoot);
  const runtimeEnv = resolveWorkspaceProcessEnv(policy.workspaceRoot);
  const pythonExecutable = pythonExecutableLabel(python);
  let pythonRunnable = false;
  let pythonVersion = "unknown";

  if (!policy.configFound) {
    pushCheck(reportChecks, "error", "Workspace config", `Configured config file not found: ${policy.configPath}`, [
      "Create or select an existing pipeline config and set cortexmark.configPath.",
      "Open docs for setup and config guidance.",
    ]);
  } else {
    pushCheck(reportChecks, "ok", "Workspace config", `Config file found at ${policy.configPath}`, [
      "Open config to inspect settings.",
    ]);
  }
  if (policy.configNotes.length > 0) {
    pushCheck(reportChecks, "warn", "Path policy", policy.configNotes.join(" "));
  }

  if (!python) {
    pushCheck(reportChecks, "error", "Python executable", "No python executable was resolved.", [
      "Set cortexmark.pythonPath explicitly to a valid Python executable.",
      "Open settings and point to a workspace interpreter.",
      "Open settings to install the backend with the correct interpreter.",
    ]);
  } else {
    const pythonProbe = await runPythonCheck(
      python,
      "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}\")",
      runtimeEnv,
    );
    if (!pythonProbe.ok) {
      pushCheck(reportChecks, "error", "Python executable", `${pythonExecutable} cannot run python code.`, [
        "Set a working python executable in cortexmark.pythonPath.",
        "Ensure selected interpreter is installed and reachable.",
        "Use the Setup Wizard to open environment settings.",
      ]);
    } else {
      pythonRunnable = true;
      pythonVersion = pythonProbe.stdout || "unknown";
      const pv = pythonVersionParts(pythonVersion);
      if (!pv || pv.major < 3 || (pv.major === 3 && pv.minor < PYTHON_MIN_MINOR)) {
        pushCheck(reportChecks, "error", "Python version", `Resolved Python is ${pythonVersion}; minimum is ${MIN_PYTHON_VERSION}.`, [
          "Create/use Python 3.11+ interpreter and update cortexmark.pythonPath.",
        ]);
      } else {
        pushCheck(reportChecks, "ok", "Python executable", `${pythonExecutable} (Python ${pythonVersion})`);
      }

      const backend = await runPythonCheck(python, "import cortexmark; print('ok')", runtimeEnv);
      if (backend.ok) {
        pushCheck(
          reportChecks,
          "ok",
          "Python backend",
          "cortexmark package is importable.",
          ["Run pipeline commands from CortexMark view."],
        );
      } else {
        pushCheck(
          reportChecks,
          "error",
          "Python backend",
          "cortexmark is not importable in the selected interpreter.",
          [
            "Install backend with pip install cortexmark.",
            "Use the same Python interpreter for all setup and pipeline commands.",
            "Open docs for full installation steps.",
          ],
        );
      }

      const doclingMissingMessage =
        "docling is required for 'docling' and optional fallback in 'dual' for full extraction.";
      if (engine === "docling" || engine === "dual") {
        const docling = await runPythonCheck(
          python,
          "import importlib.util; print('yes' if importlib.util.find_spec('docling') else 'no')",
          runtimeEnv,
        );
        if (docling.ok && docling.stdout === "yes") {
          pushCheck(
            reportChecks,
            "ok",
            "Engine dependency",
            `docling is available for engine = ${engine}.`,
          );
        } else {
          const status = engine === "docling" ? "error" : "warn";
          pushCheck(
            reportChecks,
            status,
            "Engine dependency",
            `${doclingMissingMessage} Current engine is "${engine}" and docling is not importable.`,
            engine === "docling"
              ? ["Install docling dependency: pip install \"cortexmark[docling]\"."]
              : ["Install docling if you expect dual-mode conversion with docling output quality."],
          );
        }
      } else {
        pushCheck(reportChecks, "ok", "Engine dependency", "Engine is markitdown; docling is not required.");
      }

      const systemDeps = await runPythonCheck(
        python,
        [
          "from cortexmark.paths import resolve_binary",
          "print('pdftotext=' + str(bool(resolve_binary(\"pdftotext\"))))",
          "print('tesseract=' + str(bool(resolve_binary(\"tesseract\"))))",
        ].join("; "),
        runtimeEnv,
      );
      const [pdfokLine, tesseractLine] = systemDeps.stdout.split("\n").map((line) => line.trim());
      const hasPdf = pdfokLine?.includes("True");
      const hasTess = tesseractLine?.includes("True");
      if (engine === "docling" || engine === "dual") {
        if (hasPdf && hasTess) {
          pushCheck(reportChecks, "ok", "System tools", "poppler-utils and tesseract are available.");
        } else if (hasPdf && !hasTess) {
          pushCheck(reportChecks, "warn", "System tools", "pdftotext found, tesseract not found.", [
            "Install tesseract-ocr and ensure it is on PATH if OCR is used.",
          ]);
        } else if (!hasPdf && hasTess) {
          pushCheck(reportChecks, "warn", "System tools", "tesseract found, pdftotext not found.", [
            "Install poppler-utils and ensure pdftotext is on PATH.",
          ]);
        } else {
          pushCheck(reportChecks, "warn", "System tools", "Both pdftotext and tesseract were not found on PATH.", [
            "Install poppler-utils and tesseract-ocr.",
          ]);
        }
      } else {
        pushCheck(reportChecks, "ok", "System tools", "Engine does not require docling-specific system tools.");
      }
    }
  }

  const errors = reportChecks.filter((x) => x.status === "error").length;
  const warnings = reportChecks.filter((x) => x.status === "warn").length;
  return {
    generatedAt: now,
    workspace: policy.workspaceRoot,
    python,
    pythonRunnable,
    pythonVersion,
    defaultEngine: engine,
    pathPolicy: {
      configPath: policy.configPath,
      configFound: policy.configFound,
      configNotes: [...policy.configNotes],
      dataRoot: policy.dataRoot,
      sessionsRoot: policy.sessionsRoot,
      outputRoots: policy.outputRoots,
      sessionStorePath: policy.sessionStorePath,
    },
    checks: reportChecks,
    healthy: errors === 0,
    errors,
    warnings,
  };
}

function formatDoctorReport(report: EnvironmentDoctorReport): string[] {
  const lines: string[] = [];
  lines.push("╭─ CortexMark Environment Doctor ───────────────────────────────────────────");
  lines.push(`Workspace: ${report.workspace}`);
  lines.push(`Python executable: ${report.python || "n/a"}`);
  lines.push(`Python version: ${report.pythonVersion}`);
  lines.push(`Default engine: ${report.defaultEngine}`);
  lines.push("");
  lines.push("Resolved paths:");
  lines.push(`  Config:    ${report.pathPolicy.configPath}${report.pathPolicy.configFound ? "" : " (missing)"}`);
  lines.push(`  Config notes: ${report.pathPolicy.configNotes.join(" | ") || "none"}`);
  lines.push(`  Data root: ${report.pathPolicy.dataRoot}`);
  lines.push(`  Sessions root: ${report.pathPolicy.sessionsRoot}`);
  lines.push(`  Output raw_md: ${report.pathPolicy.outputRoots.rawMd}`);
  lines.push(`  Output cleaned_md: ${report.pathPolicy.outputRoots.cleanedMd}`);
  lines.push(`  Output chunks: ${report.pathPolicy.outputRoots.chunks}`);
  lines.push(`  Output quality: ${report.pathPolicy.outputRoots.quality}`);
  lines.push(`  Output semantic chunks: ${report.pathPolicy.outputRoots.semanticChunks}`);
  lines.push(`  Session store: ${report.pathPolicy.sessionStorePath}`);
  lines.push(`Generated: ${report.generatedAt}`);
  lines.push("");
  for (const check of report.checks) {
    const icon = check.status === "ok" ? "✓" : check.status === "warn" ? "⚠" : "✗";
    lines.push(`${icon} ${check.title}: ${check.details}`);
    if (check.fixes?.length) {
      for (const fix of check.fixes) {
        lines.push(`   - ${fix}`);
      }
    }
  }
  lines.push("");
  lines.push(
    `Summary: ${report.errors} error(s), ${report.warnings} warning(s), backend-ready: ${report.healthy ? "yes" : "no"}`,
  );
  lines.push("╰──────────────────────────────────────────────────────────────────────");
  return lines;
}

async function showDoctorReport(report: EnvironmentDoctorReport): Promise<void> {
  const ch = doctorChannel;
  ch.clear();
  for (const line of formatDoctorReport(report)) {
    ch.appendLine(line);
  }
  ch.show(true);
}

async function runSetupInstallSuggestion(python: string, engineHint: "docling" | "markitdown" | "dual"): Promise<void> {
  const packageArg = engineHint === "markitdown" ? "cortexmark" : "\"cortexmark[docling]\"";
  const installLine = `${pythonExecutableLabel(python)} -m pip install ${packageArg}`;
  const terminal = vscode.window.createTerminal("CortexMark Setup");
  terminal.show();
  terminal.sendText(installLine);
}

async function openDocs(): Promise<void> {
  await vscode.env.openExternal(vscode.Uri.parse(DOCS_URL));
}

async function runEnvironmentWizard(context: vscode.ExtensionContext, policy: PathPolicy): Promise<EnvironmentDoctorReport> {
  const python = await resolvePython(policy.workspaceRoot);
  const report = await runEnvironmentDoctor(policy);
  await showDoctorReport(report);

  if (report.healthy) {
    await vscode.window.showInformationMessage(
      "Environment check passed. CortexMark backend is usable with current workspace settings.",
    );
    return report;
  }

  const quickActions = report.pythonRunnable
    ? ["Install backend now", "Open Settings", "Open Setup Guide", "Open Config", "Re-run Doctor"]
    : ["Open Settings", "Open Setup Guide", "Open Config", "Re-run Doctor"];
    const action = await vscode.window.showInformationMessage(
      `Environment issues detected (${report.errors} error, ${report.warnings} warning). Pick next step.`,
      ...quickActions,
  );
  switch (action) {
    case "Install backend now":
      if (report.pythonRunnable) {
        await runSetupInstallSuggestion(python, report.defaultEngine as "docling" | "markitdown" | "dual");
      }
      break;
    case "Open Settings":
      await vscode.commands.executeCommand("workbench.action.openSettings", "cortexmark");
      break;
    case "Open Setup Guide":
      await openDocs();
      break;
    case "Open Config":
      await cmdOpenConfig(policy);
      break;
    case "Re-run Doctor":
      await cmdEnvironmentDoctor(context, policy);
      break;
    default:
      break;
  }
  return report;
}

async function cmdRunSetupWizard(context: vscode.ExtensionContext, policy: PathPolicy): Promise<void> {
  await runEnvironmentWizard(context, policy);
}

async function cmdEnvironmentDoctor(context: vscode.ExtensionContext, policy: PathPolicy): Promise<void> {
  const report = await runEnvironmentDoctor(policy);
  await showDoctorReport(report);
  const summary = `${report.errors} error(s), ${report.warnings} warning(s)`;
  if (report.healthy) {
    void vscode.window.showInformationMessage(`CortexMark Environment Doctor: all checks passed (${summary}).`);
  } else {
    void vscode.window.showWarningMessage(`CortexMark Environment Doctor: ${summary} require attention.`);
  }
}

async function maybeShowStartupEnvironmentGuidance(context: vscode.ExtensionContext, policy: PathPolicy): Promise<void> {
  const wsRoot = policy.workspaceRoot;
  const lastState = context.globalState.get<number>(`${STARTUP_DOCTOR_KEY_PREFIX}:${wsRoot}`);
  const now = Date.now();
  if (lastState && now - lastState < 24 * 60 * 60 * 1000) {
    return;
  }

  const report = await runEnvironmentDoctor(policy);
  if (!report.healthy) {
    const action = await vscode.window.showWarningMessage(
      `CortexMark setup check found ${report.errors} error(s). Run Environment Doctor for details.`,
      "Run Environment Doctor",
      "Setup Wizard",
      "Later",
    );
    if (action === "Run Environment Doctor") {
      await cmdEnvironmentDoctor(context, policy);
    } else if (action === "Setup Wizard") {
      await runEnvironmentWizard(context, policy);
    }
  }
  await context.globalState.update(`${STARTUP_DOCTOR_KEY_PREFIX}:${wsRoot}`, now);
}

function actionSummary(report: EnvironmentDoctorReport): string {
  if (report.healthy) {
    return "Environment check passed.";
  }
  if (report.errors > 0) {
    return `${report.errors} blocking issue(s) found.`;
  }
  return `${report.warnings} advisory issue(s) found.`;
}

async function checkAndGuideBeforeRun(context: vscode.ExtensionContext, policy: PathPolicy): Promise<boolean> {
  const report = await runEnvironmentDoctor(policy);
  if (report.healthy) {
    return true;
  }

  const action = await vscode.window.showWarningMessage(
    `CortexMark environment not ready: ${actionSummary(report)} Open Environment Doctor for fixes.`,
    "Run Environment Doctor",
    "Run Setup Wizard",
    "Proceed anyway",
  );
  if (action === "Run Environment Doctor") {
    await cmdEnvironmentDoctor(context, policy);
    return false;
  }
  if (action === "Run Setup Wizard") {
    await runEnvironmentWizard(context, policy);
    return false;
  }
  // Advanced users can still proceed intentionally, but we keep the warning visible first.
  return action === "Proceed anyway";
}


/** Build backend env overrides so one session stays fully inside its own workspace. */
function sessionCommandEnv(
  sessionPaths: {
    dataDir: string;
    inputDir: string;
    outputsDir: string;
    rawDir: string;
    cleanedDir: string;
    chunksDir: string;
    qualityDir: string;
    semanticDir: string;
    manifestPath: string;
  },
): NodeJS.ProcessEnv {
  return {
    CORTEXMARK_DATA_DIR: sessionPaths.dataDir,
    DATA_DIR: sessionPaths.dataDir,
    CORTEXMARK_RAW_DATA_DIR: sessionPaths.inputDir,
    RAW_DATA_DIR: sessionPaths.inputDir,
    CORTEXMARK_OUTPUT_DIR: sessionPaths.outputsDir,
    OUTPUT_DIR: sessionPaths.outputsDir,
    CORTEXMARK_OUTPUT_RAW_MD: sessionPaths.rawDir,
    OUTPUT_RAW_MD: sessionPaths.rawDir,
    CORTEXMARK_OUTPUT_CLEANED_MD: sessionPaths.cleanedDir,
    OUTPUT_CLEANED_MD: sessionPaths.cleanedDir,
    CORTEXMARK_OUTPUT_CHUNKS: sessionPaths.chunksDir,
    OUTPUT_CHUNKS: sessionPaths.chunksDir,
    CORTEXMARK_REPORT_DIR: sessionPaths.qualityDir,
    REPORT_DIR: sessionPaths.qualityDir,
    CORTEXMARK_OUTPUT_SEMANTIC_CHUNKS: sessionPaths.semanticDir,
    OUTPUT_SEMANTIC_CHUNKS: sessionPaths.semanticDir,
    CORTEXMARK_MANIFEST_FILE: sessionPaths.manifestPath,
    MANIFEST_FILE: sessionPaths.manifestPath,
  };
}

/** Try to obtain the interpreter path from the Microsoft Python extension. */
async function getPythonFromExtension(): Promise<string | undefined> {
  try {
    const pythonExt = vscode.extensions.getExtension("ms-python.python");
    if (!pythonExt) return undefined;
    if (!pythonExt.isActive) {
      await pythonExt.activate();
    }
    const api = pythonExt.exports;
    const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri;
    // New environments API (2023+)
    if (api?.environments?.getActiveEnvironmentPath) {
      const env = api.environments.getActiveEnvironmentPath(wsFolder);
      if (env?.path) return env.path;
    }
    // Legacy API
    if (api?.settings?.getExecutionDetails) {
      const details = api.settings.getExecutionDetails(wsFolder);
      if (details?.execCommand?.[0]) return details.execCommand[0];
    }
  } catch {
    // Python extension not available or API changed — ignore
  }
  return undefined;
}

function resolveVirtualEnvPython(venvRoot: string | undefined, workspaceRoot: string): string | undefined {
  if (!venvRoot) {
    return undefined;
  }
  const resolvedRoot = resolveExecutableOverride(venvRoot, workspaceRoot);
  const candidates = [
    path.join(resolvedRoot, "bin", "python"),
    path.join(resolvedRoot, "bin", "python3"),
    path.join(resolvedRoot, "Scripts", "python.exe"),
  ];
  return candidates.find((candidate) => fs.existsSync(candidate));
}

/** Resolve the Python executable: explicit setting → env/.env → venv discovery → Python extension → safe executables. */
async function resolvePython(wsRoot: string): Promise<string> {
  const configuredPython = getExplicitStringSetting("pythonPath");
  const normalizedConfigured = configuredPython ? resolveExecutableOverride(configuredPython, wsRoot) : "";
  if (normalizedConfigured && normalizedConfigured !== "python3") {
    return normalizedConfigured;
  }

  const envPython = resolveWorkspaceEnvValue(wsRoot, PYTHON_PATH_ENV_KEYS);
  if (envPython) {
    return resolveExecutableOverride(envPython, wsRoot);
  }

  const activatedVirtualEnv = resolveVirtualEnvPython(resolveWorkspaceEnvValue(wsRoot, ["VIRTUAL_ENV"]), wsRoot);
  if (activatedVirtualEnv) {
    return activatedVirtualEnv;
  }

  // Auto-detect workspace venv
  const candidates = [
    path.join(wsRoot, ".venv", "bin", "python"),
    path.join(wsRoot, ".venv", "bin", "python3"),
    path.join(wsRoot, "venv", "bin", "python"),
    path.join(wsRoot, "venv", "bin", "python3"),
    path.join(wsRoot, ".venv", "Scripts", "python.exe"),
    path.join(wsRoot, "venv", "Scripts", "python.exe"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      return c;
    }
  }

  // Try the Microsoft Python extension's selected interpreter
  const extPython = await getPythonFromExtension();
  if (extPython) return extPython;

  // Backward-compatible fallbacks for empty/default settings.
  if (normalizedConfigured) {
    return normalizedConfigured;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function requireActiveSession(mgr: SessionManager): Session | undefined {
  const session = mgr.active();
  if (!session) {
    void vscode.window.showWarningMessage("Create or select an active session first.");
    return undefined;
  }
  return session;
}

function countStagedPdfs(session: Session, policy: PathPolicy): { existing: number; missing: number } {
  let existing = 0;
  let missing = 0;
  for (const file of session.files) {
    const absolutePath = path.resolve(policy.workspaceRoot, file.relativePath);
    if (fs.existsSync(absolutePath)) {
      existing++;
    } else {
      missing++;
    }
  }
  return { existing, missing };
}

function ensureSessionHasRunnableInput(session: Session, policy: PathPolicy): boolean {
  const { existing, missing } = countStagedPdfs(session, policy);
  if (existing === 0) {
    const detail = missing > 0
      ? ` The session has ${missing} tracked PDF(s), but none exist in the session workspace anymore. Re-add them first.`
      : " Add at least one PDF to the active session first.";
    void vscode.window.showWarningMessage(`No runnable PDFs found for "${session.name}".${detail}`);
    return false;
  }
  if (missing > 0) {
    void vscode.window.showWarningMessage(
      `${missing} staged PDF(s) are missing from "${session.name}". Existing PDFs will still run, but you should re-add the missing ones.`,
    );
  }
  return true;
}

// ═══════════════════════════════════════════════════════════════════════════
// Activation
// ═══════════════════════════════════════════════════════════════════════════

export function activate(context: vscode.ExtensionContext): void {
  const wsRoot = root();
  if (!wsRoot) return;
  const policy = resolvePathPolicy(wsRoot);

  // ── Gentle startup guidance (non-blocking, once per day per workspace) ──
  void maybeShowStartupEnvironmentGuidance(context, policy);

  // ── Core services ──────────────────────────────────────────────────────
  const sessions = new SessionManager(policy);
  const runner = new PipelineRunner();
  const preview = new PreviewPanel(context.extensionUri, policy, sessions);
  const dashboard = new DashboardPanel(context.extensionUri, policy, sessions);
  const chat = new ChatViewProvider(context.extensionUri);

  // ── Tree view ──────────────────────────────────────────────────────────
  const tree = new SessionTreeProvider(sessions, policy);
  sessions.onDidChange(() => {
    tree.refresh();
    dashboard.refresh();
  });

  let activeWatchers: vscode.Disposable[] = [];
  const rebuildPathWatchers = (): void => {
    for (const disposable of activeWatchers) {
      disposable.dispose();
    }
    activeWatchers = [];

    fs.mkdirSync(policy.sessionsRoot, { recursive: true });
    const sessionWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(vscode.Uri.file(policy.sessionsRoot), "**"),
    );
    const refreshViews = (): void => {
      tree.refresh();
      dashboard.refresh();
    };
    sessionWatcher.onDidCreate(refreshViews);
    sessionWatcher.onDidChange(refreshViews);
    sessionWatcher.onDidDelete(refreshViews);

    activeWatchers = [sessionWatcher];
  };
  rebuildPathWatchers();

  // ── Register everything ────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("cortexmarkPanel", tree),
    vscode.window.registerWebviewViewProvider(DashboardPanel.viewId, dashboard),
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, chat),
    { dispose: () => activeWatchers.forEach((watcher) => watcher.dispose()) },
    sessions,
    runner,
    preview,

    // Session commands
    vscode.commands.registerCommand("cortexmark.refresh", () => {
      tree.refresh();
      dashboard.refresh();
    }),
    vscode.commands.registerCommand("cortexmark.newSession", () => cmdNewSession(sessions)),
    vscode.commands.registerCommand("cortexmark.deleteSession", (item?: PipelineItem) =>
      cmdDeleteSession(sessions, policy, item),
    ),
    vscode.commands.registerCommand("cortexmark.setActiveSession", (item?: PipelineItem) =>
      cmdSetActive(sessions, item),
    ),
    vscode.commands.registerCommand("cortexmark.processSession", () =>
      processActiveSession(context, sessions, runner, policy),
    ),
    vscode.commands.registerCommand("cortexmark.addPdf", () => cmdAddPdf(context, runner, sessions, policy)),
    vscode.commands.registerCommand("cortexmark.addFolder", () => cmdAddFolder(context, runner, sessions, policy)),

    // Pipeline commands (use spawn runner)
    vscode.commands.registerCommand("cortexmark.runFull", () => cmdRunFull(context, runner, policy, sessions)),
    vscode.commands.registerCommand("cortexmark.runConvert", () => cmdRunConvert(context, runner, policy, sessions)),
    vscode.commands.registerCommand("cortexmark.runQA", () => cmdRunQA(context, runner, policy, sessions, dashboard)),
    vscode.commands.registerCommand("cortexmark.runDiff", () => cmdRunDiff(context, runner, policy, sessions)),
    vscode.commands.registerCommand("cortexmark.checkEnvironment", () => cmdEnvironmentDoctor(context, policy)),
    vscode.commands.registerCommand("cortexmark.setupWizard", () => cmdRunSetupWizard(context, policy)),
    vscode.commands.registerCommand("cortexmark.openConfig", () => cmdOpenConfig(policy)),
    vscode.commands.registerCommand("cortexmark.openOutput", (arg?: string | PipelineItem) =>
      cmdOpenOutput(policy, arg),
    ),
    vscode.commands.registerCommand("cortexmark.deleteOutput", (item?: PipelineItem) =>
      cmdDeleteOutput(item, tree),
    ),

    // Analysis commands
    vscode.commands.registerCommand("cortexmark.runCrossRef", () =>
      cmdRunAnalysis(context, runner, policy, sessions, "crossRef", dashboard),
    ),
    vscode.commands.registerCommand("cortexmark.runAlgorithm", () =>
      cmdRunAnalysis(context, runner, policy, sessions, "algorithm", dashboard),
    ),
    vscode.commands.registerCommand("cortexmark.runNotation", () =>
      cmdRunAnalysis(context, runner, policy, sessions, "notation", dashboard),
    ),
    vscode.commands.registerCommand("cortexmark.runSemanticChunk", () =>
      cmdRunAnalysis(context, runner, policy, sessions, "semanticChunk", dashboard),
    ),
    vscode.commands.registerCommand("cortexmark.runAllAnalysis", () =>
      cmdRunAllAnalysis(context, runner, policy, sessions, dashboard),
    ),

    // Preview commands
    vscode.commands.registerCommand("cortexmark.previewFile", (arg?: string | PipelineItem) =>
      cmdPreview(preview, policy, arg),
    ),
    vscode.commands.registerCommand("cortexmark.refreshPreview", () => preview.refresh()),
    vscode.commands.registerCommand("cortexmark.refreshDashboard", () => dashboard.refresh()),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (
        event.affectsConfiguration("cortexmark.configPath") ||
        event.affectsConfiguration("cortexmark.dataRoot") ||
        event.affectsConfiguration("cortexmark.outputRoot") ||
        event.affectsConfiguration("cortexmark.sessionStorePath")
      ) {
        Object.assign(policy, resolvePathPolicy(wsRoot));
        rebuildPathWatchers();
        tree.refresh();
        dashboard.refresh();
      }
    }),
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
    placeHolder: "e.g. Research Batch",
  });
  if (!name) return;
  const requestedRoot = mgr.pathsFor(name).sessionRoot;
  if (mgr.sessions().some((session) => path.resolve(mgr.pathsFor(session).sessionRoot) === path.resolve(requestedRoot))) {
    void vscode.window.showWarningMessage(`A session named "${name}" already maps to ${requestedRoot}. Choose a different name.`);
    return;
  }
  const s = mgr.create(name);
  void vscode.window.showInformationMessage(`Session "${s.name}" created and set as active.`);
}

async function cmdDeleteSession(mgr: SessionManager, policy: PathPolicy, item?: PipelineItem): Promise<void> {
  const id = item?.sessionId;
  if (!id) return;
  const session = mgr.get(id);
  if (!session) return;
  const answer = await vscode.window.showWarningMessage(
    `Delete session "${session.name}" and its copied inputs/outputs?`,
    { modal: true },
    "Delete",
  );
  if (answer === "Delete") {
    cleanSessionOutputs(session, policy);
    mgr.delete(id);
  }
}

/** Remove the session-local workspace (copied inputs + outputs). */
function cleanSessionOutputs(
  session: { name: string; files: { relativePath: string }[] },
  policy: PathPolicy,
): void {
  const sessionRoot = assertWithinRoot(
    policy.sessionsRoot,
    policy.sessionOutputs(session.name).sessionRoot,
    "Session workspace",
  );
  if (fs.existsSync(sessionRoot)) {
    fs.rmSync(sessionRoot, { recursive: true, force: true });
  }
}

function cmdSetActive(mgr: SessionManager, item?: PipelineItem): void {
  const id = item?.sessionId;
  if (id) {
    mgr.setActive(id);
  }
}

async function cmdAddPdf(
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  mgr: SessionManager,
  policy: PathPolicy,
): Promise<void> {
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
    defaultUri: vscode.Uri.file(policy.dataRoot),
    title: "Select PDF files to add",
  });
  if (!uris?.length) return;
  const count = addPdfUris(mgr, active.id, uris);
  if (count > 0) {
    void vscode.window.showInformationMessage(`Added ${count} PDF(s) to "${active.name}".`);
    if (cfg<boolean>("autoProcess")) {
      await processActiveSession(context, mgr, runner, policy);
    }
  }
}

async function cmdAddFolder(
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  mgr: SessionManager,
  policy: PathPolicy,
): Promise<void> {
  const active = mgr.active();
  if (!active) {
    void vscode.window.showWarningMessage("Create a session first.");
    return;
  }
  const uris = await vscode.window.showOpenDialog({
    canSelectMany: false,
    canSelectFiles: false,
    canSelectFolders: true,
    defaultUri: vscode.Uri.file(policy.dataRoot),
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
  const count = addPdfUris(mgr, active.id, pdfUris);
  if (count > 0) {
    void vscode.window.showInformationMessage(`Added ${count} PDF(s) from folder to "${active.name}".`);
    if (cfg<boolean>("autoProcess")) {
      await processActiveSession(context, mgr, runner, policy);
    }
  }
}

function addPdfUris(mgr: SessionManager, sessionId: string, uris: readonly vscode.Uri[]): number {
  let count = 0;
  for (const uri of uris) {
    if (mgr.stagePdf(sessionId, uri.fsPath)) {
      count++;
    }
  }
  return count;
}

// ═══════════════════════════════════════════════════════════════════════════
// Process active session (spawn-based)
// ═══════════════════════════════════════════════════════════════════════════

async function processActiveSession(
  context: vscode.ExtensionContext,
  mgr: SessionManager,
  runner: PipelineRunner,
  policy: PathPolicy,
): Promise<void> {
  if (!need(policy.workspaceRoot)) return;
  const session = mgr.active();
  if (!session) {
    void vscode.window.showWarningMessage("No active session.");
    return;
  }
  if (runner.busy) {
    void vscode.window.showWarningMessage("Pipeline is already running.");
    return;
  }
  if (!ensureSessionHasRunnableInput(session, policy)) {
    return;
  }
  if (!(await checkAndGuideBeforeRun(context, policy))) {
    return;
  }
  const sessionPaths = mgr.pathsFor(session);

  // Mark queued files as processing
  mgr.bulkUpdate(session.id, "queued", "processing");

  const result = await runner.runPipeline(
    {
      python: await resolvePython(policy.workspaceRoot),
      root: policy.workspaceRoot,
      config: policy.configPath,
      engine: cfg<string>("defaultEngine"),
      input: sessionPaths.inputDir,
      env: sessionCommandEnv(sessionPaths),
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

async function cmdRunFull(
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  policy: PathPolicy,
  mgr: SessionManager,
): Promise<void> {
  if (!need(policy.workspaceRoot) || runner.busy) return;
  const session = requireActiveSession(mgr);
  if (!session) return;
  if (!ensureSessionHasRunnableInput(session, policy)) {
    return;
  }
  if (!(await checkAndGuideBeforeRun(context, policy))) return;
  const sessionPaths = mgr.pathsFor(session);
  await runner.runPipeline({
    python: await resolvePython(policy.workspaceRoot),
    root: policy.workspaceRoot,
    config: policy.configPath,
    engine: cfg<string>("defaultEngine"),
    input: sessionPaths.inputDir,
    env: sessionCommandEnv(sessionPaths),
  });
}

async function cmdRunConvert(
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  policy: PathPolicy,
  mgr: SessionManager,
): Promise<void> {
  if (!need(policy.workspaceRoot) || runner.busy) return;
  const session = requireActiveSession(mgr);
  if (!session) return;
  if (!ensureSessionHasRunnableInput(session, policy)) {
    return;
  }
  if (!(await checkAndGuideBeforeRun(context, policy))) return;
  const sessionPaths = mgr.pathsFor(session);
  await runner.runPipeline({
    python: await resolvePython(policy.workspaceRoot),
    root: policy.workspaceRoot,
    config: policy.configPath,
    engine: cfg<string>("defaultEngine"),
    stages: ["convert"],
    input: sessionPaths.inputDir,
    env: sessionCommandEnv(sessionPaths),
  });
}

async function cmdRunQA(
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  policy: PathPolicy,
  mgr: SessionManager,
  dashboard: DashboardPanel,
): Promise<void> {
  if (!need(policy.workspaceRoot) || runner.busy) return;
  const session = requireActiveSession(mgr);
  if (!session) return;
  if (!(await checkAndGuideBeforeRun(context, policy))) return;
  const sessionPaths = mgr.pathsFor(session);
  if (!fs.existsSync(sessionPaths.cleanedDir)) {
    void vscode.window.showWarningMessage("No cleaned Markdown output found for the active session. Run the pipeline first.");
    return;
  }
  await runner.runQA({
    python: await resolvePython(policy.workspaceRoot),
    root: policy.workspaceRoot,
    config: policy.configPath,
    input: sessionPaths.cleanedDir,
    output: mgr.reportPath(session, "qa_report.json"),
    env: sessionCommandEnv(sessionPaths),
  });
  dashboard.refresh();
}

async function cmdRunDiff(
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  policy: PathPolicy,
  mgr: SessionManager,
): Promise<void> {
  if (!need(policy.workspaceRoot) || runner.busy) return;
  if (!(await checkAndGuideBeforeRun(context, policy))) return;
  const activeSession = mgr.active();
  const activeSessionPaths = activeSession ? mgr.pathsFor(activeSession) : undefined;

  const oldDir = await vscode.window.showInputBox({
    title: "Old folder",
    prompt: "Path to old output folder",
    value: activeSessionPaths?.cleanedDir ?? policy.outputRoots.cleanedMd,
  });
  if (!oldDir) return;
  const newDir = await vscode.window.showInputBox({
    title: "New folder",
    prompt: "Path to new output folder",
    value: activeSessionPaths?.rawDir ?? policy.outputRoots.rawMd,
  });
  if (!newDir) return;

  const session = activeSession;
  const diffOutput = session
    ? mgr.reportPath(session, "diff_report.json")
    : path.join(policy.outputRoots.quality, "diff_report.json");

  await runner.runDiff({
    python: await resolvePython(policy.workspaceRoot),
    root: policy.workspaceRoot,
    config: policy.configPath,
    oldDir,
    newDir,
    output: diffOutput,
    env: activeSessionPaths ? sessionCommandEnv(activeSessionPaths) : undefined,
  });
}

async function cmdOpenConfig(policy: PathPolicy): Promise<void> {
  const wsRoot = policy.workspaceRoot;
  if (!need(wsRoot)) return;
  const p = policy.configPath;
  if (!fs.existsSync(p)) {
    const action = await vscode.window.showWarningMessage(
      `Config not found: ${p}`,
      "Open Settings",
      "Open Setup Guide",
    );
    if (action === "Open Settings") {
      await vscode.commands.executeCommand("workbench.action.openSettings", "cortexmark.configPath");
    } else if (action === "Open Setup Guide") {
      await openDocs();
    }
    return;
  }
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(p));
  await vscode.window.showTextDocument(doc, { preview: false });
}

async function cmdOpenOutput(policy: PathPolicy, arg?: string | PipelineItem): Promise<void> {
  if (!need(policy.workspaceRoot)) return;
  let rel: string | undefined;
  if (typeof arg === "string") {
    rel = arg;
  } else if (arg instanceof PipelineItem && arg.fsPath) {
    rel = arg.fsPath;
  } else if (arg instanceof PipelineItem && arg.command?.arguments?.[0]) {
    rel = arg.command.arguments[0] as string;
  }
  if (!rel) return;
  const absPath = path.isAbsolute(rel) ? rel : path.resolve(policy.workspaceRoot, rel);
  await vscode.commands.executeCommand("revealInExplorer", vscode.Uri.file(absPath));
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
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  policy: PathPolicy,
  mgr: SessionManager,
  kind: AnalysisKind,
  dashboard: DashboardPanel,
): Promise<void> {
  if (!need(policy.workspaceRoot) || runner.busy) return;
  const session = requireActiveSession(mgr);
  if (!session) return;
  if (!(await checkAndGuideBeforeRun(context, policy))) return;
  const sessionPaths = mgr.pathsFor(session);

  const inputDir = sessionPaths.cleanedDir;
  if (!fs.existsSync(inputDir)) {
    void vscode.window.showWarningMessage("No cleaned Markdown output found for the active session. Run the pipeline first.");
    return;
  }

  const python = await resolvePython(policy.workspaceRoot);

  let result;
  switch (kind) {
    case "crossRef":
      result = await runner.runCrossRef({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        output: mgr.reportPath(session, "crossref_report.json"),
        env: sessionCommandEnv(sessionPaths),
      });
      break;
    case "algorithm":
      result = await runner.runAlgorithmExtract({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        output: mgr.reportPath(session, "algorithm_report.json"),
        env: sessionCommandEnv(sessionPaths),
      });
      break;
    case "notation":
      result = await runner.runNotationGlossary({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        output: mgr.reportPath(session, "notation_report.json"),
        env: sessionCommandEnv(sessionPaths),
      });
      break;
    case "semanticChunk":
      result = await runner.runSemanticChunk({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        outputDir: sessionPaths.semanticDir,
        env: sessionCommandEnv(sessionPaths),
      });
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
  context: vscode.ExtensionContext,
  runner: PipelineRunner,
  policy: PathPolicy,
  mgr: SessionManager,
  dashboard: DashboardPanel,
): Promise<void> {
  if (!need(policy.workspaceRoot) || runner.busy) return;
  const session = requireActiveSession(mgr);
  if (!session) return;
  if (!(await checkAndGuideBeforeRun(context, policy))) return;
  const sessionPaths = mgr.pathsFor(session);

  const inputDir = sessionPaths.cleanedDir;
  if (!fs.existsSync(inputDir)) {
    void vscode.window.showWarningMessage("No cleaned Markdown output found for the active session. Run the pipeline first.");
    return;
  }

  const python = await resolvePython(policy.workspaceRoot);

  const analyses: [string, () => Promise<import("./pipelineRunner").RunResult>][] = [
    [
      "Cross References",
      () => runner.runCrossRef({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        output: mgr.reportPath(session, "crossref_report.json"),
        env: sessionCommandEnv(sessionPaths),
      }),
    ],
    [
      "Algorithm Extraction",
      () => runner.runAlgorithmExtract({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        output: mgr.reportPath(session, "algorithm_report.json"),
        env: sessionCommandEnv(sessionPaths),
      }),
    ],
    [
      "Notation Glossary",
      () => runner.runNotationGlossary({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        output: mgr.reportPath(session, "notation_report.json"),
        env: sessionCommandEnv(sessionPaths),
      }),
    ],
    [
      "Semantic Chunking",
      () => runner.runSemanticChunk({
        python,
        root: policy.workspaceRoot,
        input: inputDir,
        outputDir: sessionPaths.semanticDir,
        env: sessionCommandEnv(sessionPaths),
      }),
    ],
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

function cmdPreview(preview: PreviewPanel, policy: PathPolicy, arg?: string | PipelineItem): void {
  if (!need(policy.workspaceRoot)) return;

  let filePath: string | undefined;

  if (typeof arg === "string") {
    filePath = path.isAbsolute(arg) ? arg : path.resolve(policy.workspaceRoot, arg);
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
