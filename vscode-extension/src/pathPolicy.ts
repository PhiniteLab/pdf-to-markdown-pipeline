import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as vscode from "vscode";
import { buildSessionWorkspacePaths } from "./sessionLayout";

const DEFAULT_CONFIG_FILE = "configs/pipeline.yaml";
const WORKSPACE_DOTENV_FILE = ".env";
const DEFAULT_SESSIONS_ROOT = "sessions";
const DEFAULT_PATHS = {
  dataRaw: "data/raw",
  outputRawMd: "outputs/raw_md",
  outputCleanedMd: "outputs/cleaned_md",
  outputChunks: "outputs/chunks",
  outputQuality: "outputs/quality",
  outputSemanticChunks: "outputs/semantic_chunks",
};
const CONFIG_PATH_ENV_KEYS = ["CORTEXMARK_CONFIG_PATH", "PIPELINE_CONFIG"];
const DATA_ROOT_ENV_KEYS = ["CORTEXMARK_DATA_ROOT", "PIPELINE_DATA_ROOT"];
const OUTPUT_ROOT_ENV_KEYS = ["CORTEXMARK_OUTPUT_ROOT", "PIPELINE_OUTPUT_ROOT"];
const OUTPUT_RAW_MD_ENV_KEYS = ["CORTEXMARK_OUTPUT_RAW_MD"];
const OUTPUT_CLEANED_MD_ENV_KEYS = ["CORTEXMARK_OUTPUT_CLEANED_MD"];
const OUTPUT_CHUNKS_ENV_KEYS = ["CORTEXMARK_OUTPUT_CHUNKS"];
const OUTPUT_QUALITY_ENV_KEYS = ["CORTEXMARK_OUTPUT_QUALITY"];
const OUTPUT_SEMANTIC_CHUNKS_ENV_KEYS = ["CORTEXMARK_OUTPUT_SEMANTIC_CHUNKS"];
const SESSIONS_ROOT_ENV_KEYS = ["CORTEXMARK_SESSIONS_DIR", "SESSIONS_DIR"];
const SESSION_STORE_ENV_KEYS = ["CORTEXMARK_SESSION_STORE_PATH", "CORTEXMARK_SESSION_STORE"];

interface RawConfiguredPaths {
  dataRaw?: string;
  outputRawMd?: string;
  outputCleanedMd?: string;
  outputChunks?: string;
  outputQuality?: string;
  outputSemanticChunks?: string;
}

export interface SessionOutputPaths {
  sessionRoot: string;
  dataDir: string;
  inputDir: string;
  outputsDir: string;
  rawDir: string;
  cleanedDir: string;
  chunksDir: string;
  qualityDir: string;
  semanticDir: string;
  manifestPath: string;
  reportPath(fileName: string): string;
}

export interface PathPolicy {
  workspaceRoot: string;
  configPath: string;
  configDir: string;
  configFound: boolean;
  configNotes: string[];
  dataRoot: string;
  sessionsRoot: string;
  outputRoots: {
    rawMd: string;
    cleanedMd: string;
    chunks: string;
    quality: string;
    semanticChunks: string;
  };
  manifestPath: string;
  sessionStorePath: string;
  legacySessionStorePath: string;
  sessionOutputs(sessionName: string): SessionOutputPaths;
}

interface ParsedConfigPaths {
  dataRaw?: string;
  outputRawMd?: string;
  outputCleanedMd?: string;
  outputChunks?: string;
  outputQuality?: string;
  outputSemanticChunks?: string;
}

// Keep legacy compatibility for other code in this repo.
export type EffectivePaths = Omit<PathPolicy, "configNotes" | "sessionOutputs"> & {
  outputRoot: string;
  rawMdRoot: string;
  cleanedMdRoot: string;
  chunksRoot: string;
  qualityRoot: string;
  semanticChunksRoot: string;
};

interface SettingInspection<T> {
  explicit?: T;
  effective: T;
}

function trimQuotes(raw: string): string {
  const trimmed = raw.trim();
  if ((trimmed.startsWith("\"") && trimmed.endsWith("\"")) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function expandHomeDirectory(raw: string): string {
  if (raw === "~") {
    return os.homedir();
  }
  if (raw.startsWith("~/") || raw.startsWith("~\\")) {
    return path.join(os.homedir(), raw.slice(2));
  }
  return raw;
}

function replaceWorkspaceTokens(raw: string, workspaceRoot: string): string {
  return expandHomeDirectory(raw)
    .replace(/\$\{workspaceFolder\}/g, workspaceRoot)
    .replace(/\$\{workspaceFolderBasename\}/g, path.basename(workspaceRoot));
}

function isNonEmptyString(raw: unknown): raw is string {
  return typeof raw === "string" && trimQuotes(raw).trim().length > 0;
}

function looksLikePath(raw: string): boolean {
  return raw.startsWith(".") || raw.startsWith("~") || raw.includes("/") || raw.includes("\\") || /^[A-Za-z]:/.test(raw);
}

function resolveConfiguredPath(raw: string | undefined, workspaceRoot: string, fallback: string, baseDir = workspaceRoot): string {
  const expanded = raw ? replaceWorkspaceTokens(trimQuotes(raw), workspaceRoot) : "";
  if (!expanded) return path.resolve(baseDir, fallback);
  return path.isAbsolute(expanded) ? path.resolve(expanded) : path.resolve(baseDir, expanded);
}

export function resolveExecutableOverride(raw: string, workspaceRoot: string): string {
  const expanded = replaceWorkspaceTokens(trimQuotes(raw), workspaceRoot);
  if (!expanded) {
    return "";
  }
  if (looksLikePath(expanded)) {
    return path.isAbsolute(expanded) ? path.resolve(expanded) : path.resolve(workspaceRoot, expanded);
  }
  return expanded;
}

function resolveConfiguredOrFallback(
  configured: string | undefined,
  workspaceRoot: string,
  fallback: string,
  configuredBaseDir: string,
  fallbackBaseDir = workspaceRoot,
): string {
  const trimmed = configured ? trimQuotes(configured).trim() : "";
  if (trimmed) {
    return resolveConfiguredPath(trimmed, workspaceRoot, fallback, configuredBaseDir);
  }
  return resolveConfiguredPath(undefined, workspaceRoot, fallback, fallbackBaseDir);
}

function parseYamlPathOverrides(configPath: string): ParsedConfigPaths {
  if (!fs.existsSync(configPath)) return {};

  try {
    const rawText = fs.readFileSync(configPath, "utf-8");
    const lines = rawText.split(/\r?\n/);
    const parsed: ParsedConfigPaths = {};
    let inPaths = false;
    let pathsIndent = 0;

    for (const line of lines) {
      const text = (line.split("#", 1)[0] ?? "").trim();
      if (!text) continue;

      const indent = line.length - line.trimStart().length;
      if (!inPaths) {
        if (/^paths\s*:\s*$/.test(text)) {
          inPaths = true;
          pathsIndent = indent;
        }
        continue;
      }

      if (indent <= pathsIndent) {
        inPaths = /^paths\s*:\s*$/.test(text);
        if (inPaths) pathsIndent = indent;
        continue;
      }

      const kvMatch = text.match(/^([A-Za-z0-9_\-]+)\s*:\s*(.*)$/);
      if (!kvMatch) continue;

      const key = kvMatch[1];
      const value = trimQuotes((kvMatch[2] ?? "").trim());
      switch (key) {
        case "data_raw":
          parsed.dataRaw = value;
          break;
        case "output_raw_md":
          parsed.outputRawMd = value;
          break;
        case "output_cleaned_md":
          parsed.outputCleanedMd = value;
          break;
        case "output_chunks":
          parsed.outputChunks = value;
          break;
        case "output_quality":
          parsed.outputQuality = value;
          break;
        case "output_semantic_chunks":
          parsed.outputSemanticChunks = value;
          break;
        default:
          break;
      }
    }

    return parsed;
  } catch {
    return {};
  }
}

function stripInlineComment(raw: string): string {
  let inSingle = false;
  let inDouble = false;

  for (let index = 0; index < raw.length; index += 1) {
    const char = raw[index];
    if (char === "'" && !inDouble) {
      inSingle = !inSingle;
      continue;
    }
    if (char === "\"" && !inSingle) {
      inDouble = !inDouble;
      continue;
    }
    if (char === "#" && !inSingle && !inDouble) {
      const prev = index > 0 ? raw[index - 1] : "";
      if (!prev || /\s/.test(prev)) {
        return raw.slice(0, index).trimEnd();
      }
    }
  }
  return raw.trim();
}

function readWorkspaceDotEnv(workspaceRoot: string): Record<string, string> {
  const filePath = path.join(workspaceRoot, WORKSPACE_DOTENV_FILE);
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const parsed: Record<string, string> = {};
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    for (const line of raw.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }
      const candidate = trimmed.startsWith("export ") ? trimmed.slice("export ".length).trim() : trimmed;
      const match = candidate.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
      if (!match) {
        continue;
      }
      const key = match[1];
      const value = trimQuotes(stripInlineComment(match[2] ?? ""));
      parsed[key] = value;
    }
  } catch {
    return {};
  }
  return parsed;
}

function inspectSetting<T>(key: string, fallback: T): SettingInspection<T> {
  const inspected = vscode.workspace.getConfiguration("cortexmark").inspect<T>(key);
  const explicit = inspected?.workspaceFolderValue ?? inspected?.workspaceValue ?? inspected?.globalValue;
  const effective = explicit ?? inspected?.defaultValue ?? fallback;
  return { explicit, effective };
}

export function getExplicitStringSetting(key: string): string | undefined {
  const inspected = inspectSetting<string | undefined>(key, undefined);
  return isNonEmptyString(inspected.explicit) ? inspected.explicit : undefined;
}

export function resolveWorkspaceEnvValue(workspaceRoot: string, keys: readonly string[]): string | undefined {
  for (const key of keys) {
    const value = process.env[key];
    if (isNonEmptyString(value)) {
      return value;
    }
  }
  const dotEnv = readWorkspaceDotEnv(workspaceRoot);
  for (const key of keys) {
    const value = dotEnv[key];
    if (isNonEmptyString(value)) {
      return value;
    }
  }
  return undefined;
}

export function resolveWorkspaceProcessEnv(workspaceRoot: string): NodeJS.ProcessEnv {
  return {
    ...readWorkspaceDotEnv(workspaceRoot),
    ...process.env,
  };
}

function resolvePathConfig(configPath: string): { configFound: boolean; configNotes: string[]; configured: ParsedConfigPaths } {
  if (!configPath) {
    return { configFound: false, configNotes: ["No config path set in settings."], configured: {} };
  }
  if (!fs.existsSync(configPath)) {
    return { configFound: false, configNotes: [`Configured config not found: ${configPath}`], configured: {} };
  }
  return { configFound: true, configNotes: [], configured: parseYamlPathOverrides(configPath) };
}

function resolveOutputsForSession(sessionsRoot: string, sessionName: string): SessionOutputPaths {
  const workspace = buildSessionWorkspacePaths(sessionsRoot, sessionName);
  return {
    sessionRoot: workspace.sessionRoot,
    dataDir: workspace.dataDir,
    inputDir: workspace.inputDir,
    outputsDir: workspace.outputsDir,
    rawDir: workspace.rawDir,
    cleanedDir: workspace.cleanedDir,
    chunksDir: workspace.chunksDir,
    qualityDir: workspace.qualityDir,
    semanticDir: workspace.semanticDir,
    manifestPath: workspace.manifestPath,
    reportPath(fileName: string): string {
      return path.join(workspace.qualityDir, fileName);
    },
  };
}

export function resolveConfigPath(workspaceRoot: string): string {
  const configuredSetting = getExplicitStringSetting("configPath");
  const envConfigured = resolveWorkspaceEnvValue(workspaceRoot, CONFIG_PATH_ENV_KEYS);
  const rawConfigPath = configuredSetting || envConfigured || DEFAULT_CONFIG_FILE;
  return resolveConfiguredPath(rawConfigPath, workspaceRoot, DEFAULT_CONFIG_FILE);
}

export function resolvePathPolicy(workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath): PathPolicy {
  const wsRoot = workspaceRoot ?? process.cwd();
  const rawConfigPath = getExplicitStringSetting("configPath")
    || resolveWorkspaceEnvValue(wsRoot, CONFIG_PATH_ENV_KEYS)
    || DEFAULT_CONFIG_FILE;
  const configPath = resolveConfiguredPath(rawConfigPath, wsRoot, DEFAULT_CONFIG_FILE);
  const configDir = path.dirname(configPath);
  const configState = resolvePathConfig(configPath);

  const dataRootSetting = getExplicitStringSetting("dataRoot");
  const dataRootEnv = resolveWorkspaceEnvValue(wsRoot, DATA_ROOT_ENV_KEYS);
  const dataRoot = dataRootSetting
    ? resolveConfiguredPath(dataRootSetting, wsRoot, DEFAULT_PATHS.dataRaw, wsRoot)
    : dataRootEnv
      ? resolveConfiguredPath(dataRootEnv, wsRoot, DEFAULT_PATHS.dataRaw, wsRoot)
    : resolveConfiguredOrFallback(
      configState.configured.dataRaw,
      wsRoot,
      DEFAULT_PATHS.dataRaw,
      configDir,
      wsRoot,
    );

  const outputRoot = getExplicitStringSetting("outputRoot") || resolveWorkspaceEnvValue(wsRoot, OUTPUT_ROOT_ENV_KEYS);
  const outputRootAbs = outputRoot ? resolveConfiguredPath(outputRoot, wsRoot, "outputs") : "";

  const rawMdEnv = resolveWorkspaceEnvValue(wsRoot, OUTPUT_RAW_MD_ENV_KEYS);
  const cleanedMdEnv = resolveWorkspaceEnvValue(wsRoot, OUTPUT_CLEANED_MD_ENV_KEYS);
  const chunksEnv = resolveWorkspaceEnvValue(wsRoot, OUTPUT_CHUNKS_ENV_KEYS);
  const qualityEnv = resolveWorkspaceEnvValue(wsRoot, OUTPUT_QUALITY_ENV_KEYS);
  const semanticEnv = resolveWorkspaceEnvValue(wsRoot, OUTPUT_SEMANTIC_CHUNKS_ENV_KEYS);

  const rawMdConfigured = resolveConfiguredOrFallback(
    configState.configured.outputRawMd,
    wsRoot,
    DEFAULT_PATHS.outputRawMd,
    configDir,
    wsRoot,
  );
  const cleanedMdConfigured = resolveConfiguredOrFallback(
    configState.configured.outputCleanedMd,
    wsRoot,
    DEFAULT_PATHS.outputCleanedMd,
    configDir,
    wsRoot,
  );
  const chunksConfigured = resolveConfiguredOrFallback(
    configState.configured.outputChunks,
    wsRoot,
    DEFAULT_PATHS.outputChunks,
    configDir,
    wsRoot,
  );
  const qualityConfigured = resolveConfiguredOrFallback(
    configState.configured.outputQuality,
    wsRoot,
    DEFAULT_PATHS.outputQuality,
    configDir,
    wsRoot,
  );
  const semanticConfigured = resolveConfiguredOrFallback(
    configState.configured.outputSemanticChunks,
    wsRoot,
    DEFAULT_PATHS.outputSemanticChunks,
    configDir,
    wsRoot,
  );

  const rawMd = outputRootAbs
    ? path.join(outputRootAbs, "raw_md")
    : rawMdEnv
      ? resolveConfiguredPath(rawMdEnv, wsRoot, DEFAULT_PATHS.outputRawMd, wsRoot)
      : rawMdConfigured;
  const cleanedMd = outputRootAbs
    ? path.join(outputRootAbs, "cleaned_md")
    : cleanedMdEnv
      ? resolveConfiguredPath(cleanedMdEnv, wsRoot, DEFAULT_PATHS.outputCleanedMd, wsRoot)
      : cleanedMdConfigured;
  const chunks = outputRootAbs
    ? path.join(outputRootAbs, "chunks")
    : chunksEnv
      ? resolveConfiguredPath(chunksEnv, wsRoot, DEFAULT_PATHS.outputChunks, wsRoot)
      : chunksConfigured;
  const quality = outputRootAbs
    ? path.join(outputRootAbs, "quality")
    : qualityEnv
      ? resolveConfiguredPath(qualityEnv, wsRoot, DEFAULT_PATHS.outputQuality, wsRoot)
      : qualityConfigured;
  const semanticChunks = outputRootAbs
    ? path.join(outputRootAbs, "semantic_chunks")
    : semanticEnv
      ? resolveConfiguredPath(semanticEnv, wsRoot, DEFAULT_PATHS.outputSemanticChunks, wsRoot)
      : semanticConfigured;

  const manifestPath = outputRootAbs
    ? path.join(outputRootAbs, ".manifest.json")
    : path.join(path.dirname(quality), ".manifest.json");

  const sessionStoreOverride = getExplicitStringSetting("sessionStorePath")
    || resolveWorkspaceEnvValue(wsRoot, SESSION_STORE_ENV_KEYS);
  const sessionStorePath = sessionStoreOverride
    ? resolveConfiguredPath(sessionStoreOverride, wsRoot, ".cortexmark/sessions.json")
    : path.join(wsRoot, ".cortexmark", "sessions.json");
  const legacySessionStorePath = path.join(wsRoot, ".phinitelab-pdf-pipeline", "sessions.json");
  const sessionsRootOverride = resolveWorkspaceEnvValue(wsRoot, SESSIONS_ROOT_ENV_KEYS);
  const sessionsRoot = sessionsRootOverride
    ? resolveConfiguredPath(sessionsRootOverride, wsRoot, DEFAULT_SESSIONS_ROOT)
    : path.join(wsRoot, DEFAULT_SESSIONS_ROOT);

  const outputRoots = {
    rawMd,
    cleanedMd,
    chunks,
    quality,
    semanticChunks,
  };

  return {
    workspaceRoot: wsRoot,
    configPath,
    configDir,
    configFound: configState.configFound,
    configNotes: configState.configNotes,
    dataRoot,
    sessionsRoot,
    outputRoots,
    manifestPath,
    sessionStorePath,
    legacySessionStorePath,
    sessionOutputs(sessionName: string): SessionOutputPaths {
      return resolveOutputsForSession(sessionsRoot, sessionName);
    },
  };
}

export function resolveEffectivePaths(workspaceRoot: string): EffectivePaths {
  const policy = resolvePathPolicy(workspaceRoot);
  const outputRoot = deriveCommonOutputRoot(policy.outputRoots);
  return {
    ...policy,
    outputRoot,
    rawMdRoot: policy.outputRoots.rawMd,
    cleanedMdRoot: policy.outputRoots.cleanedMd,
    chunksRoot: policy.outputRoots.chunks,
    qualityRoot: policy.outputRoots.quality,
    semanticChunksRoot: policy.outputRoots.semanticChunks,
  };
}

function deriveCommonOutputRoot(roots: PathPolicy["outputRoots"]): string {
  const parents = Object.values(roots).map((r) => path.dirname(r));
  const first = parents[0];
  if (parents.every((entry) => entry === first)) {
    return first;
  }
  const fallbackBase = path.dirname(first);
  return path.join(fallbackBase, "outputs");
}

export function deriveSessionManifestPath(manifestPath: string, sessionName: string): string {
  return path.join(path.dirname(manifestPath), `.manifest-${sessionName}.json`);
}
