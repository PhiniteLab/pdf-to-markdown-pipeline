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
  private progressResolve: (() => void) | null = null;

  constructor() {
    this.output = vscode.window.createOutputChannel("CortexMark");
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
    opts: { python: string; root: string; config: string; engine: string; stages?: string[]; input?: string; sessionName?: string },
    onLine?: (line: string) => void,
  ): Promise<RunResult> {
    const args = [
      "-m", "cortexmark.run_pipeline",
      "--config", path.resolve(opts.root, opts.config),
      "--engine", opts.engine,
    ];
    if (opts.input) {
      args.push("--input", opts.input);
    }
    if (opts.sessionName) {
      args.push("--session-name", opts.sessionName);
    }
    if (opts.stages?.length) {
      args.push("--stages", ...opts.stages);
    }
    const label = opts.stages?.length
      ? `Pipeline [${opts.stages.join(", ")}]`
      : "Full Pipeline";
    return this.execWithProgress(opts.python, args, opts.root, label);
  }

  runQA(opts: {
    python: string; root: string; config: string; input: string; output: string;
  }): Promise<RunResult> {
    return this.exec(
      opts.python,
      [
        "-m", "cortexmark.qa_pipeline",
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
        "-m", "cortexmark.diff",
        "--config", path.resolve(opts.root, opts.config),
        "--old", opts.oldDir,
        "--new", opts.newDir,
        "--output", opts.output,
      ],
      opts.root,
      "Diff Report",
    );
  }

  // ── Analysis module commands ─────────────────────────────────────────

  runCrossRef(opts: {
    python: string; root: string; input: string; output: string;
  }): Promise<RunResult> {
    return this.execWithProgress(
      opts.python,
      ["-m", "cortexmark.cross_ref", "--input", opts.input, "--output", opts.output],
      opts.root,
      "Cross Reference Analysis",
    );
  }

  runAlgorithmExtract(opts: {
    python: string; root: string; input: string; output: string;
  }): Promise<RunResult> {
    return this.execWithProgress(
      opts.python,
      ["-m", "cortexmark.algorithm_extract", "--input", opts.input, "--output", opts.output],
      opts.root,
      "Algorithm Extraction",
    );
  }

  runNotationGlossary(opts: {
    python: string; root: string; input: string; output: string;
  }): Promise<RunResult> {
    return this.execWithProgress(
      opts.python,
      ["-m", "cortexmark.notation_glossary", "--input", opts.input, "--output", opts.output],
      opts.root,
      "Notation Glossary",
    );
  }

  runSemanticChunk(opts: {
    python: string; root: string; input: string; outputDir: string;
  }): Promise<RunResult> {
    return this.execWithProgress(
      opts.python,
      ["-m", "cortexmark.semantic_chunk", "--input", opts.input, "--output-dir", opts.outputDir],
      opts.root,
      "Semantic Chunking",
    );
  }

  // ── Progress-wrapped execution ───────────────────────────────────────

  private async execWithProgress(
    python: string,
    args: string[],
    cwd: string,
    label: string,
  ): Promise<RunResult> {
    return await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: label,
        cancellable: true,
      },
      (progress, token) => {
        let lineCount = 0;
        const onLine = (line: string) => {
          lineCount++;
          // Check for pipeline-style progress markers
          const pctMatch = line.match(/(\d+)%/);
          if (pctMatch) {
            progress.report({ increment: 0, message: `${pctMatch[1]}%` });
          } else {
            // Show the last line as status
            const short = line.length > 60 ? line.substring(0, 57) + "..." : line;
            progress.report({ message: short });
          }
        };

        token.onCancellationRequested(() => {
          if (this.proc) {
            this.proc.kill("SIGTERM");
          }
        });

        return this.exec(python, args, cwd, label, onLine);
      },
    );
  }

  dispose(): void {
    this.proc?.kill();
    this.output.dispose();
  }
}
