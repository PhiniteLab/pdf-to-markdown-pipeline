import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import type { FileStatus, PdfFile, Session, SessionStore } from "./types";

function genId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substring(2, 8);
}

export class SessionManager implements vscode.Disposable {
  private store: SessionStore = { sessions: [] };
  private readonly storePath: string;

  private readonly _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChange = this._onDidChange.event;

  constructor(private readonly root: string) {
    const dir = path.join(root, ".pdf-pipeline");
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    this.storePath = path.join(dir, "sessions.json");
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
