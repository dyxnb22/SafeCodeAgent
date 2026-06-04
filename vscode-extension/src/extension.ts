/**
 * SafeCode Agent VS Code Extension.
 *
 * EXPERIMENTAL: IDE bridge surface is not a stable contract.
 *
 * Architecture:
 * - Spawns `sac api jsonrpc` as a child process over stdio.
 * - Uses JSON-RPC 2.0 (newline-delimited) for ask/edit/apply/report.
 * - Diff preview opens the pending unified diff in the editor.
 * - Approval prompt uses a VS Code modal before calling apply.
 * - No telemetry. No marketplace publishing in this batch.
 * - Does not bypass approval, audit, rollback, or MCP/CLI safety gates.
 */

import * as vscode from "vscode";
import * as cp from "child_process";
import * as readline from "readline";

const EXTENSION_NAME = "SafeCode Agent";
const JSONRPC_VERSION = "2.0";
let _nextId = 1;

function nextId(): number {
  return _nextId++;
}

// ── JSON-RPC bridge ───────────────────────────────────────────────────────────

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number;
  method: string;
  params: Record<string, unknown>;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number;
  result?: unknown;
  error?: { code: number; message: string };
}

class SafeCodeBridge {
  private proc: cp.ChildProcess | null = null;
  private pending: Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }> =
    new Map();
  private outputChannel: vscode.OutputChannel;

  constructor(outputChannel: vscode.OutputChannel) {
    this.outputChannel = outputChannel;
  }

  private sacExecutable(): string {
    const cfg = vscode.workspace.getConfiguration("safecode");
    return cfg.get<string>("sacExecutable") ?? "sac";
  }

  start(): void {
    if (this.proc) return;

    const sac = this.sacExecutable();
    this.proc = cp.spawn(sac, ["api", "jsonrpc"], {
      cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd(),
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env },
    });

    const rl = readline.createInterface({ input: this.proc.stdout! });
    rl.on("line", (line: string) => {
      try {
        const resp: JsonRpcResponse = JSON.parse(line);
        const handler = this.pending.get(resp.id);
        if (!handler) return;
        this.pending.delete(resp.id);
        if (resp.error) {
          handler.reject(new Error(resp.error.message));
        } else {
          handler.resolve(resp.result);
        }
      } catch {
        this.outputChannel.appendLine(`[safecode] malformed response: ${line}`);
      }
    });

    this.proc.stderr?.on("data", (d: Buffer) => {
      this.outputChannel.appendLine(`[safecode stderr] ${d.toString().trim()}`);
    });

    this.proc.on("exit", () => {
      this.proc = null;
      for (const [, h] of this.pending) {
        h.reject(new Error("sac api jsonrpc process exited"));
      }
      this.pending.clear();
    });
  }

  stop(): void {
    this.proc?.kill();
    this.proc = null;
  }

  private call(method: string, params: Record<string, unknown>): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.proc) {
        this.start();
      }
      const id = nextId();
      const req: JsonRpcRequest = { jsonrpc: JSONRPC_VERSION, id, method, params };
      this.pending.set(id, { resolve, reject });
      this.proc!.stdin!.write(JSON.stringify(req) + "\n");
    });
  }

  async ask(question: string): Promise<string> {
    const result = (await this.call("ask", { question })) as { answer: string };
    return result.answer;
  }

  async edit(task: string): Promise<string> {
    const result = (await this.call("edit", { task })) as { status: string; patch_id?: string };
    return result.status;
  }

  async apply(): Promise<string> {
    const result = (await this.call("apply", {})) as { status: string };
    return result.status;
  }

  async report(): Promise<string> {
    const result = (await this.call("report", {})) as { report: string };
    return result.report;
  }
}

// ── Extension lifecycle ───────────────────────────────────────────────────────

let bridge: SafeCodeBridge | null = null;
let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel(EXTENSION_NAME);
  bridge = new SafeCodeBridge(outputChannel);
  bridge.start();

  context.subscriptions.push(
    vscode.commands.registerCommand("safecode.ask", async () => {
      const question = await vscode.window.showInputBox({
        prompt: "Ask SafeCode Agent",
        placeHolder: "What does this function do?",
      });
      if (!question) return;
      try {
        const answer = await bridge!.ask(question);
        outputChannel.appendLine(`[ask] ${answer}`);
        outputChannel.show();
      } catch (e) {
        vscode.window.showErrorMessage(`SafeCode ask failed: ${e}`);
      }
    }),

    vscode.commands.registerCommand("safecode.edit", async () => {
      const task = await vscode.window.showInputBox({
        prompt: "Describe the edit for SafeCode Agent",
        placeHolder: "Fix the bug in authenticate()",
      });
      if (!task) return;
      try {
        const status = await bridge!.edit(task);
        vscode.window.showInformationMessage(
          `SafeCode edit: ${status}. Use 'SafeCode: Apply Pending Patch' to apply.`
        );
      } catch (e) {
        vscode.window.showErrorMessage(`SafeCode edit failed: ${e}`);
      }
    }),

    vscode.commands.registerCommand("safecode.apply", async () => {
      // Approval prompt is a VS Code modal — user must confirm before apply.
      const confirm = await vscode.window.showWarningMessage(
        "Apply the SafeCode pending patch to your workspace?",
        { modal: true },
        "Apply"
      );
      if (confirm !== "Apply") return;
      try {
        const status = await bridge!.apply();
        vscode.window.showInformationMessage(`SafeCode apply: ${status}`);
      } catch (e) {
        vscode.window.showErrorMessage(`SafeCode apply failed: ${e}`);
      }
    }),

    vscode.commands.registerCommand("safecode.rollback", () => {
      // Rollback is invoked via the CLI, not via the JSON-RPC bridge.
      const terminal = vscode.window.createTerminal(EXTENSION_NAME);
      terminal.sendText("sac rollback --last");
      terminal.show();
    }),

    vscode.commands.registerCommand("safecode.openDiff", () => {
      // Open the pending diff file in the editor for preview.
      const terminal = vscode.window.createTerminal(EXTENSION_NAME);
      terminal.sendText("sac ide open-diff");
      terminal.show();
    }),

    vscode.commands.registerCommand("safecode.apiJsonrpc", () => {
      // Allow the user to manually start the JSON-RPC bridge in a terminal.
      const terminal = vscode.window.createTerminal(EXTENSION_NAME);
      terminal.sendText("sac api jsonrpc");
      terminal.show();
    })
  );
}

export function deactivate(): void {
  bridge?.stop();
}
