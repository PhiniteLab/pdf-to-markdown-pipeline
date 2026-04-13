import * as cp from "child_process";
import * as path from "path";
import * as vscode from "vscode";

export interface RunResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export class PipelineRunner implements vscode.Disposable {
  private readonly output: vscode.OutputChannel;
  private proc: cp.ChildProcess | null = null;

  constructor() {
    this.output = vscode.window.createOutputChannel("PhiniteLab PDF Pipeline");
  }

  get busy(): boolean {
    return this.proc !== null;
  }

  show(): void {
    this.output.show(true);
  }

  // ── Generic spawn ────────────────────────────────────────────────────

  private exec(
    python: string,
    args: string[],
    cwd: string,
    label: string,
    onLine?: (line: string) => void,
  ): Promise<RunResult> {
    if (this.proc) {
      void vscode.window.showWarningMessage("A pipeline process is already running.");
      return Promise.resolve({ exitCode: -1, stdout: "", stderr: "busy" });
    }

    this.output.show(true);
    this.output.appendLine("");
    this.output.appendLine("\u2500".repeat(60));
    this.output.appendLine(`\u25B6 ${label}  ${new Date().toLocaleTimeString()}`);
    this.output.appendLine(`  ${python} ${args.join(" ")}`);
    this.output.appendLine("\u2500".repeat(60));

    return new Promise<RunResult>((resolve) => {
      const child = cp.spawn(python, args, { cwd, env: { ...process.env } });
      this.proc = child;
      let stdout = "";
      let stderr = "";

      child.stdout.on("data", (chunk: Buffer) => {
        const t = chunk.toString();
        stdout += t;
        this.output.append(t);
        for (const l of t.split("\n")) {
          if (l.trim()) {
            onLine?.(l);
          }
        }
      });

      child.stderr.on("data", (chunk: Buffer) => {
        const t = chunk.toString();
        stderr += t;
        this.output.append(t);
      });

      child.on("close", (code) => {
        this.proc = null;
        const exit = code ?? 1;
        this.output.appendLine(`\n${exit === 0 ? "\u2713" : "\u2717"} exit ${exit}\n`);
        resolve({ exitCode: exit, stdout, stderr });
      });

      child.on("error", (err) => {
        this.proc = null;
        this.output.appendLine(`\n\u2717 ${err.message}\n`);
        resolve({ exitCode: 1, stdout, stderr: `${stderr}\n${err.message}` });
      });
    });
  }

  // ── High-level commands ──────────────────────────────────────────────

  runPipeline(
    opts: { python: string; root: string; config: string; engine: string; stages?: string[] },
    onLine?: (line: string) => void,
  ): Promise<RunResult> {
    const args = [
      "-m", "phinitelab_pdf_pipeline.run_pipeline",
      "--config", path.resolve(opts.root, opts.config),
      "--engine", opts.engine,
    ];
    if (opts.stages?.length) {
      args.push("--stages", ...opts.stages);
    }
    return this.exec(opts.python, args, opts.root, "Full Pipeline", onLine);
  }

  runQA(opts: {
    python: string; root: string; config: string; input: string; output: string;
  }): Promise<RunResult> {
    return this.exec(
      opts.python,
      [
        "-m", "phinitelab_pdf_pipeline.qa_pipeline",
        "--config", path.resolve(opts.root, opts.config),
        "--input", opts.input,
        "--output", opts.output,
        "--format", "both",
      ],
      opts.root,
      "QA Report",
    );
  }

  runDiff(opts: {
    python: string; root: string; config: string; oldDir: string; newDir: string; output: string;
  }): Promise<RunResult> {
    return this.exec(
      opts.python,
      [
        "-m", "phinitelab_pdf_pipeline.diff",
        "--config", path.resolve(opts.root, opts.config),
        "--old", opts.oldDir,
        "--new", opts.newDir,
        "--output", opts.output,
      ],
      opts.root,
      "Diff Report",
    );
  }

  dispose(): void {
    this.proc?.kill();
    this.output.dispose();
  }
}
