import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

const DEFAULT_CONFIG_FILE = "configs/pipeline.yaml";
const DEFAULT_PATHS = {
  dataRaw: "data/raw",
  outputRawMd: "outputs/raw_md",
  outputCleanedMd: "outputs/cleaned_md",
  outputChunks: "outputs/chunks",
  outputQuality: "outputs/quality",
  outputSemanticChunks: "outputs/semantic_chunks",
};

interface RawConfiguredPaths {
  dataRaw?: string;
  outputRawMd?: string;
  outputCleanedMd?: string;
  outputChunks?: string;
  outputQuality?: string;
  outputSemanticChunks?: string;
}

export interface SessionOutputPaths {
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

function trimQuotes(raw: string): string {
  const trimmed = raw.trim();
  if ((trimmed.startsWith("\"") && trimmed.endsWith("\"")) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function replaceWorkspaceTokens(raw: string, workspaceRoot: string): string {
  return raw
    .replace(/\$\{workspaceFolder\}/g, workspaceRoot)
    .replace(/\$\{workspaceFolderBasename\}/g, path.basename(workspaceRoot));
}

function resolveConfiguredPath(raw: string | undefined, workspaceRoot: string, fallback: string, baseDir = workspaceRoot): string {
  const expanded = raw ? replaceWorkspaceTokens(trimQuotes(raw), workspaceRoot) : "";
  if (!expanded) return path.resolve(baseDir, fallback);
  return path.isAbsolute(expanded) ? path.resolve(expanded) : path.resolve(baseDir, expanded);
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

function getWorkspaceSetting<T>(key: string, fallback: T): T {
  return vscode.workspace.getConfiguration("cortexmark").get<T>(key) ?? fallback;
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

function resolveOutputsForSession(baseRoots: PathPolicy["outputRoots"], manifestPath: string, sessionName: string): SessionOutputPaths {
  const safeSession = sessionName || "default";
  return {
    rawDir: path.join(baseRoots.rawMd, safeSession),
    cleanedDir: path.join(baseRoots.cleanedMd, safeSession),
    chunksDir: path.join(baseRoots.chunks, safeSession),
    qualityDir: path.join(baseRoots.quality, safeSession),
    semanticDir: path.join(baseRoots.semanticChunks, safeSession),
    manifestPath: path.join(path.dirname(manifestPath), `.manifest-${safeSession}.json`),
    reportPath(fileName: string): string {
      return path.join(baseRoots.quality, safeSession, fileName);
    },
  };
}

export function resolveConfigPath(workspaceRoot: string): string {
  const configured = (getWorkspaceSetting("configPath", DEFAULT_CONFIG_FILE) || DEFAULT_CONFIG_FILE) as string;
  return path.isAbsolute(configured) ? configured : path.resolve(workspaceRoot, configured);
}

export function resolvePathPolicy(workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath): PathPolicy {
  const wsRoot = workspaceRoot ?? process.cwd();
  const rawConfigPath = getWorkspaceSetting<string>("configPath", DEFAULT_CONFIG_FILE);
  const configPath = resolveConfiguredPath(rawConfigPath, wsRoot, DEFAULT_CONFIG_FILE);
  const configDir = path.dirname(configPath);
  const configState = resolvePathConfig(configPath);

  const dataRootSetting = getWorkspaceSetting("dataRoot", "");
  const dataRoot = dataRootSetting
    ? resolveConfiguredPath(dataRootSetting, wsRoot, DEFAULT_PATHS.dataRaw, wsRoot)
    : resolveConfiguredOrFallback(
      configState.configured.dataRaw,
      wsRoot,
      DEFAULT_PATHS.dataRaw,
      configDir,
      wsRoot,
    );

  const outputRoot = getWorkspaceSetting("outputRoot", "");
  const outputRootAbs = outputRoot ? resolveConfiguredPath(outputRoot, wsRoot, "outputs") : "";

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

  const rawMd = outputRootAbs ? path.join(outputRootAbs, "raw_md") : rawMdConfigured;
  const cleanedMd = outputRootAbs ? path.join(outputRootAbs, "cleaned_md") : cleanedMdConfigured;
  const chunks = outputRootAbs ? path.join(outputRootAbs, "chunks") : chunksConfigured;
  const quality = outputRootAbs ? path.join(outputRootAbs, "quality") : qualityConfigured;
  const semanticChunks = outputRootAbs ? path.join(outputRootAbs, "semantic_chunks") : semanticConfigured;

  const manifestPath = outputRootAbs
    ? path.join(outputRootAbs, ".manifest.json")
    : path.join(path.dirname(quality), ".manifest.json");

  const sessionStoreOverride = getWorkspaceSetting("sessionStorePath", "");
  const sessionStorePath = sessionStoreOverride
    ? resolveConfiguredPath(sessionStoreOverride, wsRoot, ".cortexmark/sessions.json")
    : path.join(wsRoot, ".cortexmark", "sessions.json");
  const legacySessionStorePath = path.join(wsRoot, ".phinitelab-pdf-pipeline", "sessions.json");

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
    outputRoots,
    manifestPath,
    sessionStorePath,
    legacySessionStorePath,
    sessionOutputs(sessionName: string): SessionOutputPaths {
      return resolveOutputsForSession(outputRoots, manifestPath, sessionName);
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
