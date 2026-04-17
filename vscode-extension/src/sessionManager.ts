import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import type { FileStatus, PdfFile, Session, SessionStore } from "./types";
import type { PathPolicy, SessionOutputPaths } from "./pathPolicy";

export interface SessionPaths {
  rawDir: string;
  cleanedDir: string;
  chunksDir: string;
  qualityDir: string;
  semanticDir: string;
  manifestPath: string;
}

function genId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 8);
}

export class SessionManager implements vscode.Disposable {
  private store: SessionStore = { sessions: [] };
  private readonly storePath: string;
  private readonly legacyStorePath: string;

  private readonly _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChange = this._onDidChange.event;

  constructor(private readonly policy: PathPolicy) {
    const dir = path.dirname(this.policy.sessionStorePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    this.storePath = this.policy.sessionStorePath;
    this.legacyStorePath = this.policy.legacySessionStorePath;
    if (!fs.existsSync(this.storePath) && fs.existsSync(this.legacyStorePath)) {
      fs.copyFileSync(this.legacyStorePath, this.storePath);
    }
    this.load();
  }

  // ── Persistence ──────────────────────────────────────────────────────

  private load(): void {
    try {
      if (fs.existsSync(this.storePath)) {
        this.store = JSON.parse(fs.readFileSync(this.storePath, "utf-8"));
      }
    } catch {
      this.store = { sessions: [] };
    }
  }

  private save(): void {
    fs.writeFileSync(this.storePath, JSON.stringify(this.store, null, 2), "utf-8");
    this._onDidChange.fire();
  }

  // ── Queries ──────────────────────────────────────────────────────────

  sessions(): readonly Session[] {
    return this.store.sessions;
  }

  active(): Session | undefined {
    return this.store.sessions.find((s) => s.isActive);
  }

  get(id: string): Session | undefined {
    return this.store.sessions.find((s) => s.id === id);
  }

  pathsFor(sessionOrName: Session | string): SessionPaths {
    const sessionName = typeof sessionOrName === "string" ? sessionOrName : sessionOrName.name;
    const out = this.policy.sessionOutputs(sessionName);
    return {
      rawDir: out.rawDir,
      cleanedDir: out.cleanedDir,
      chunksDir: out.chunksDir,
      qualityDir: out.qualityDir,
      semanticDir: out.semanticDir,
      manifestPath: out.manifestPath,
    };
  }

  reportPath(sessionOrName: Session | string, fileName: string): string {
    return path.join(this.pathsFor(sessionOrName).qualityDir, fileName);
  }

  outputPathForFile(filePath: string): Session | undefined {
    const normalized = path.resolve(filePath);
    for (const session of this.store.sessions) {
      const outputs = this.pathsFor(session);
      const candidates = [outputs.cleanedDir, outputs.rawDir, outputs.chunksDir, outputs.semanticDir, outputs.qualityDir];
      if (candidates.some((root) => normalized === path.resolve(root) || normalized.startsWith(`${path.resolve(root)}${path.sep}`))) {
        return session;
      }
    }
    return undefined;
  }

  sessionOutputPaths(sessionName: string): SessionOutputPaths {
    return this.policy.sessionOutputs(sessionName);
  }

  // ── Mutations ────────────────────────────────────────────────────────

  create(name: string): Session {
    for (const s of this.store.sessions) {
      s.isActive = false;
    }
    const session: Session = {
      id: genId(),
      name,
      createdAt: new Date().toISOString(),
      files: [],
      isActive: true,
    };
    this.store.sessions.unshift(session);
    this.save();
    return session;
  }

  delete(id: string): void {
    this.store.sessions = this.store.sessions.filter((s) => s.id !== id);
    this.save();
  }

  setActive(id: string): void {
    for (const s of this.store.sessions) {
      s.isActive = s.id === id;
    }
    this.save();
  }

  addFile(sessionId: string, name: string, relativePath: string): PdfFile | undefined {
    const session = this.store.sessions.find((s) => s.id === sessionId);
    if (!session) return undefined;
    if (session.files.some((f) => f.relativePath === relativePath)) return undefined;
    const file: PdfFile = {
      id: genId(),
      name,
      relativePath,
      status: "queued",
      addedAt: new Date().toISOString(),
    };
    session.files.push(file);
    this.save();
    return file;
  }

  updateFile(sessionId: string, fileId: string, status: FileStatus, error?: string): void {
    const session = this.store.sessions.find((s) => s.id === sessionId);
    const file = session?.files.find((f) => f.id === fileId);
    if (!file) return;
    file.status = status;
    if (status === "done") {
      file.completedAt = new Date().toISOString();
    }
    if (error) {
      file.errorMessage = error;
    }
    this.save();
  }

  bulkUpdate(sessionId: string, from: FileStatus, to: FileStatus): void {
    const session = this.store.sessions.find((s) => s.id === sessionId);
    if (!session) return;
    let changed = false;
    for (const f of session.files) {
      if (f.status === from) {
        f.status = to;
        if (to === "done") {
          f.completedAt = new Date().toISOString();
        }
        changed = true;
      }
    }
    if (changed) this.save();
  }

  dispose(): void {
    this._onDidChange.dispose();
  }
}
