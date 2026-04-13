import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";
import type { SessionManager } from "./sessionManager";
import type { FileStatus } from "./types";

// ── Tree Item ────────────────────────────────────────────────────────────

export class PipelineItem extends vscode.TreeItem {
  readonly sessionId?: string;
  readonly fileId?: string;
  readonly fsPath?: string;

  constructor(
    label: string,
    state: vscode.TreeItemCollapsibleState,
    contextValue: string,
    opts?: {
      icon?: vscode.ThemeIcon;
      desc?: string;
      cmd?: vscode.Command;
      sessionId?: string;
      fileId?: string;
      tooltip?: string;
      fsPath?: string;
    },
  ) {
    super(label, state);
    this.contextValue = contextValue;
    if (opts?.icon) this.iconPath = opts.icon;
    if (opts?.desc !== undefined) this.description = opts.desc;
    if (opts?.cmd) this.command = opts.cmd;
    if (opts?.tooltip) this.tooltip = opts.tooltip;
    this.sessionId = opts?.sessionId;
    this.fileId = opts?.fileId;
    this.fsPath = opts?.fsPath;
  }
}

// ── Status icons ─────────────────────────────────────────────────────────

const STATUS_ICON: Record<FileStatus, { id: string; color: string }> = {
  queued:     { id: "circle-outline",  color: "disabledForeground" },
  processing: { id: "sync~spin",      color: "notificationsInfoIcon.foreground" },
  done:       { id: "check",          color: "testing.iconPassed" },
  error:      { id: "error",          color: "testing.iconFailed" },
};

// ── Static data ──────────────────────────────────────────────────────────

const ACTIONS: Array<{ label: string; desc: string; ctx: string; icon: string; cmd: string }> = [
  { label: "Run Full Pipeline",  desc: "convert \u2192 clean \u2192 chunk \u2192 render", ctx: "action.runFull",    icon: "play-circle", cmd: "pdfPipeline.runFull" },
  { label: "Convert Only",       desc: "PDF \u2192 Markdown",                              ctx: "action.runConvert", icon: "play",        cmd: "pdfPipeline.runConvert" },
  { label: "Generate QA Report", desc: "quality metrics",                                  ctx: "action.runQA",      icon: "graph",       cmd: "pdfPipeline.runQA" },
  { label: "Compare Folders",    desc: "diff two output dirs",                             ctx: "action.runDiff",    icon: "diff",        cmd: "pdfPipeline.runDiff" },
  { label: "Open Config",        desc: "pipeline.yaml",                                    ctx: "action.openConfig", icon: "gear",        cmd: "pdfPipeline.openConfig" },
];

const OUTPUTS: Array<{ label: string; desc: string; rel: string }> = [
  { label: "raw_md",     desc: "converted outputs", rel: "outputs/raw_md" },
  { label: "cleaned_md", desc: "cleaned outputs",   rel: "outputs/cleaned_md" },
  { label: "chunks",     desc: "chunked outputs",   rel: "outputs/chunks" },
  { label: "quality",    desc: "QA & diff reports",  rel: "outputs/quality" },
];

// ── Tree Data Provider ───────────────────────────────────────────────────

export class SessionTreeProvider implements vscode.TreeDataProvider<PipelineItem> {
  private _onChange = new vscode.EventEmitter<PipelineItem | undefined | void>();
  readonly onDidChangeTreeData = this._onChange.event;

  constructor(private readonly mgr: SessionManager, private readonly wsRoot: string) {}

  refresh(): void {
    this._onChange.fire();
  }

  getTreeItem(el: PipelineItem): PipelineItem {
    return el;
  }

  getChildren(el?: PipelineItem): PipelineItem[] {
    // ── Root level ─────────────────────────────────────────────────────
    if (!el) {
      return [
        new PipelineItem("Sessions", vscode.TreeItemCollapsibleState.Expanded, "group.sessions", {
          icon: new vscode.ThemeIcon("library"),
        }),
        new PipelineItem("Actions", vscode.TreeItemCollapsibleState.Expanded, "group.actions", {
          icon: new vscode.ThemeIcon("rocket"),
        }),
        new PipelineItem("Outputs", vscode.TreeItemCollapsibleState.Collapsed, "group.outputs", {
          icon: new vscode.ThemeIcon("folder"),
        }),
      ];
    }

    // ── Sessions group ─────────────────────────────────────────────────
    if (el.contextValue === "group.sessions") {
      const items: PipelineItem[] = [];
      for (const s of this.mgr.sessions()) {
        const done = s.files.filter((f) => f.status === "done").length;
        const total = s.files.length;
        const desc = total > 0 ? `${done}/${total} done` : "empty";
        const prefix = s.isActive ? "\u2605 " : "";
        items.push(
          new PipelineItem(
            `${prefix}${s.name}`,
            vscode.TreeItemCollapsibleState.Collapsed,
            s.isActive ? "session.active" : "session",
            {
              icon: new vscode.ThemeIcon("folder", s.isActive ? new vscode.ThemeColor("charts.yellow") : undefined),
              desc,
              sessionId: s.id,
              tooltip: `Created: ${new Date(s.createdAt).toLocaleString()}`,
            },
          ),
        );
      }
      // "+ New Session" button
      items.push(
        new PipelineItem("New Session", vscode.TreeItemCollapsibleState.None, "newSession", {
          icon: new vscode.ThemeIcon("add"),
          cmd: { title: "New Session", command: "pdfPipeline.newSession" },
        }),
      );
      return items;
    }

    // ── Session children → files ───────────────────────────────────────
    if (el.contextValue === "session" || el.contextValue === "session.active") {
      const session = this.mgr.get(el.sessionId!);
      if (!session || session.files.length === 0) {
        return [
          new PipelineItem("Drop PDFs into data/raw/", vscode.TreeItemCollapsibleState.None, "hint", {
            icon: new vscode.ThemeIcon("info"),
          }),
        ];
      }
      return session.files.map((f) => {
        const si = STATUS_ICON[f.status];
        const absPath = path.resolve(this.wsRoot, f.relativePath);
        return new PipelineItem(f.name, vscode.TreeItemCollapsibleState.None, `sessionFile.${f.status}`, {
          icon: new vscode.ThemeIcon(si.id, new vscode.ThemeColor(si.color)),
          desc: f.status,
          sessionId: session.id,
          fileId: f.id,
          cmd: { title: "Open File", command: "vscode.open", arguments: [vscode.Uri.file(absPath)] },
        });
      });
    }

    // ── Actions group ──────────────────────────────────────────────────
    if (el.contextValue === "group.actions") {
      return ACTIONS.map(
        (a) =>
          new PipelineItem(a.label, vscode.TreeItemCollapsibleState.None, a.ctx, {
            icon: new vscode.ThemeIcon(a.icon),
            desc: a.desc,
            cmd: { title: a.label, command: a.cmd },
          }),
      );
    }

    // ── Outputs group ──────────────────────────────────────────────────
    if (el.contextValue === "group.outputs") {
      return OUTPUTS.map(
        (o) =>
          new PipelineItem(o.label, vscode.TreeItemCollapsibleState.Collapsed, "output.folder", {
            icon: new vscode.ThemeIcon("folder-opened"),
            desc: o.desc,
            fsPath: path.resolve(this.wsRoot, o.rel),
          }),
      );
    }

    // ── Output directory contents ────────────────────────────────────────
    if (el.contextValue === "output.folder" || el.contextValue === "output.dir") {
      const dir = el.fsPath;
      if (!dir || !fs.existsSync(dir)) {
        return [
          new PipelineItem("(empty)", vscode.TreeItemCollapsibleState.None, "hint", {
            icon: new vscode.ThemeIcon("info"),
          }),
        ];
      }
      const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => {
        if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      if (entries.length === 0) {
        return [
          new PipelineItem("(empty)", vscode.TreeItemCollapsibleState.None, "hint", {
            icon: new vscode.ThemeIcon("info"),
          }),
        ];
      }
      return entries.map((entry) => {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          return new PipelineItem(entry.name, vscode.TreeItemCollapsibleState.Collapsed, "output.dir", {
            icon: new vscode.ThemeIcon("folder"),
            fsPath: fullPath,
          });
        }
        const item = new PipelineItem(entry.name, vscode.TreeItemCollapsibleState.None, "output.file", {
          cmd: { title: "Open File", command: "vscode.open", arguments: [vscode.Uri.file(fullPath)] },
          fsPath: fullPath,
        });
        item.resourceUri = vscode.Uri.file(fullPath);
        return item;
      });
    }

    return [];
  }
}
