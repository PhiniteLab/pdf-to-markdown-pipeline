import * as path from "path";

export interface SessionWorkspacePaths {
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
}

export function sanitizeSessionSegment(raw: string, fallback = "default"): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    return fallback;
  }
  const normalized = trimmed
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "-")
    .replace(/\s+/g, " ")
    .replace(/^\.+$/, fallback)
    .replace(/^\.+/, "")
    .trim()
    .replace(/[. ]+$/g, "");
  return normalized || fallback;
}

export function isWithinRoot(rootPath: string, candidatePath: string): boolean {
  const resolvedRoot = path.resolve(rootPath);
  const resolvedCandidate = path.resolve(candidatePath);
  return resolvedCandidate === resolvedRoot || resolvedCandidate.startsWith(`${resolvedRoot}${path.sep}`);
}

export function assertWithinRoot(rootPath: string, candidatePath: string, label: string): string {
  const resolvedCandidate = path.resolve(candidatePath);
  if (!isWithinRoot(rootPath, resolvedCandidate)) {
    throw new Error(`${label} escaped the allowed session root: ${resolvedCandidate}`);
  }
  return resolvedCandidate;
}

export function buildSessionWorkspacePaths(sessionsRoot: string, sessionName: string): SessionWorkspacePaths {
  const safeSession = sanitizeSessionSegment(sessionName || "default");
  const sessionRoot = path.join(sessionsRoot, safeSession);
  const dataDir = path.join(sessionRoot, "data");
  const inputDir = path.join(dataDir, "raw");
  const outputsDir = path.join(sessionRoot, "outputs");
  const qualityDir = path.join(outputsDir, "quality");
  return {
    sessionRoot,
    dataDir,
    inputDir,
    outputsDir,
    rawDir: path.join(outputsDir, "raw_md"),
    cleanedDir: path.join(outputsDir, "cleaned_md"),
    chunksDir: path.join(outputsDir, "chunks"),
    qualityDir,
    semanticDir: path.join(outputsDir, "semantic_chunks"),
    manifestPath: path.join(outputsDir, ".manifest.json"),
  };
}
