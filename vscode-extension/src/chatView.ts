import * as vscode from "vscode";
import type { SessionManager } from "./sessionManager";
import type { PipelineRunner } from "./pipelineRunner";

export class ChatViewProvider implements vscode.WebviewViewProvider {
  static readonly viewId = "pdfPipelineChat";

  private view?: vscode.WebviewView;
  private pending: Array<{ role: string; text: string }> = [];

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly sessions: SessionManager,
    private readonly runner: PipelineRunner,
  ) {}

  // ── Public API ─────────────────────────────────────────────────────────

  postMessage(role: "user" | "system", text: string): void {
    if (this.view?.visible) {
      void this.view.webview.postMessage({ type: "addMessage", role, text });
    } else {
      this.pending.push({ role, text });
    }
  }

  // ── WebviewViewProvider ────────────────────────────────────────────────

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this.view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };

    webviewView.webview.html = this.buildHtml();

    webviewView.webview.onDidReceiveMessage((msg: { type: string; text: string }) => {
      if (msg.type === "userMessage") {
        void this.handleMessage(msg.text);
      }
    });

    // Flush buffered messages
    for (const m of this.pending) {
      void webviewView.webview.postMessage({ type: "addMessage", role: m.role, text: m.text });
    }
    this.pending = [];
  }

  // ── Message handler ────────────────────────────────────────────────────

  private async handleMessage(text: string): Promise<void> {
    this.postMessage("user", text);
    const lower = text.trim().toLowerCase();

    // /status or durum
    if (lower === "status" || lower === "durum") {
      const s = this.sessions.active();
      if (!s) {
        this.postMessage("system", "No active session. Create one from the sidebar.");
        return;
      }
      const q = s.files.filter((f) => f.status === "queued").length;
      const p = s.files.filter((f) => f.status === "processing").length;
      const d = s.files.filter((f) => f.status === "done").length;
      const e = s.files.filter((f) => f.status === "error").length;
      this.postMessage(
        "system",
        `**${s.name}** (${s.files.length} files)\n` +
          `\u2B1C Queued: ${q}  \u23F3 Processing: ${p}  \u2705 Done: ${d}  \u274C Error: ${e}`,
      );
      return;
    }

    // /process or run or çalıştır
    if (lower === "process" || lower === "run" || lower.startsWith("çalıştır") || lower.startsWith("calistir")) {
      if (this.runner.busy) {
        this.postMessage("system", "\u23F3 A pipeline is already running.");
        return;
      }
      this.postMessage("system", "\uD83D\uDE80 Starting pipeline...");
      await vscode.commands.executeCommand("pdfPipeline.processSession");
      return;
    }

    // /qa
    if (lower === "qa" || lower === "kalite") {
      if (this.runner.busy) {
        this.postMessage("system", "\u23F3 A pipeline is already running.");
        return;
      }
      this.postMessage("system", "\uD83D\uDCCA Running QA report...");
      await vscode.commands.executeCommand("pdfPipeline.runQA");
      return;
    }

    // /help
    if (lower === "help" || lower === "yardım" || lower === "yardim") {
      this.postMessage(
        "system",
        "Commands:\n" +
          "\u2022 **status** \u2014 Active session status\n" +
          "\u2022 **process** \u2014 Run pipeline on active session\n" +
          "\u2022 **qa** \u2014 Generate QA report\n" +
          "\u2022 **help** \u2014 This message",
      );
      return;
    }

    this.postMessage("system", 'Type **help** to see available commands.');
  }

  // ── HTML ───────────────────────────────────────────────────────────────

  private buildHtml(): string {
    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:var(--vscode-font-family);
  font-size:var(--vscode-font-size);
  color:var(--vscode-foreground);
  background:var(--vscode-sideBar-background);
  display:flex;flex-direction:column;height:100vh;
}
#messages{flex:1;overflow-y:auto;padding:8px}
.msg{margin-bottom:8px;padding:6px 10px;border-radius:6px;white-space:pre-wrap;word-wrap:break-word;line-height:1.4}
.msg.user{background:var(--vscode-input-background);border:1px solid var(--vscode-input-border,transparent);margin-left:20px}
.msg.system{background:var(--vscode-textBlockQuote-background,rgba(127,127,127,.1));border-left:3px solid var(--vscode-textLink-foreground);margin-right:20px}
#bar{display:flex;padding:6px;border-top:1px solid var(--vscode-panel-border)}
#bar input{flex:1;padding:6px 8px;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border,transparent);border-radius:4px;outline:none;font:inherit}
#bar button{margin-left:4px;padding:6px 12px;background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:none;border-radius:4px;cursor:pointer;font:inherit}
#bar button:hover{background:var(--vscode-button-hoverBackground)}
</style>
</head>
<body>
<div id="messages"><div class="msg system">Welcome! Type <b>help</b> for commands.</div></div>
<div id="bar"><input id="inp" type="text" placeholder="Type a command..." /><button id="btn">Send</button></div>
<script>
const vscode=acquireVsCodeApi();
const msgs=document.getElementById("messages");
const inp=document.getElementById("inp");
function add(role,text){
  const d=document.createElement("div");
  d.className="msg "+role;
  d.innerHTML=text.replace(/\\*\\*(.+?)\\*\\*/g,"<b>$1</b>").replace(/\\n/g,"<br>");
  msgs.appendChild(d);
  msgs.scrollTop=msgs.scrollHeight;
}
function send(){
  const t=inp.value.trim();
  if(!t)return;
  inp.value="";
  vscode.postMessage({type:"userMessage",text:t});
}
document.getElementById("btn").addEventListener("click",send);
inp.addEventListener("keydown",e=>{if(e.key==="Enter")send()});
window.addEventListener("message",e=>{
  if(e.data.type==="addMessage")add(e.data.role,e.data.text);
});
</script>
</body>
</html>`;
  }
}
