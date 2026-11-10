const vscode = require("vscode");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

function findServer() {
  const candidates = [];
  if (process.env.SENSEPIN_HOME) {
    candidates.push(path.join(process.env.SENSEPIN_HOME, "fold", "lsp.py"));
  }
  candidates.push(path.join(os.homedir(), "AppData", "Local", "Sensepin", "fold", "lsp.py"));
  const folders = vscode.workspace.workspaceFolders || [];
  for (const folder of folders) {
    candidates.push(path.join(folder.uri.fsPath, "fold", "lsp.py"));
  }
  return candidates.find((item) => fs.existsSync(item)) || "";
}

class SensepinClient {
  constructor(script) {
    this.script = script;
    this.nextId = 1;
    this.buffer = Buffer.alloc(0);
    this.proc = spawn("python", [script], { stdio: ["pipe", "pipe", "pipe"] });
    this.proc.stdout.on("data", (chunk) => this.onData(chunk));
    this.proc.on("exit", () => {
      this.proc = null;
    });
  }

  send(message) {
    if (!this.proc) {
      return;
    }
    const data = Buffer.from(JSON.stringify(message), "utf8");
    const header = Buffer.from(`Content-Length: ${data.length}\r\n\r\n`, "ascii");
    this.proc.stdin.write(Buffer.concat([header, data]));
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      const split = this.buffer.indexOf("\r\n\r\n");
      if (split < 0) {
        return;
      }
      const header = this.buffer.slice(0, split).toString("ascii");
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match) {
        this.buffer = this.buffer.slice(split + 4);
        continue;
      }
      const length = Number(match[1]);
      const start = split + 4;
      if (this.buffer.length < start + length) {
        return;
      }
      const body = this.buffer.slice(start, start + length).toString("utf8");
      this.buffer = this.buffer.slice(start + length);
      this.onMessage(JSON.parse(body));
    }
  }

  onMessage(message) {
    if (message.method !== "textDocument/publishDiagnostics") {
      return;
    }
    const uri = vscode.Uri.parse(message.params.uri);
    const diagnostics = message.params.diagnostics.map((item) => {
      const start = new vscode.Position(item.range.start.line, item.range.start.character);
      const end = new vscode.Position(item.range.end.line, item.range.end.character);
      return new vscode.Diagnostic(new vscode.Range(start, end), item.message, vscode.DiagnosticSeverity.Error);
    });
    const collection = this.collection;
    if (collection) {
      collection.set(uri, diagnostics);
    }
  }
}

function activate(context) {
  const script = findServer();
  if (!script) {
    return;
  }
  const client = new SensepinClient(script);
  client.collection = vscode.languages.createDiagnosticCollection("sensepin");
  context.subscriptions.push(client.collection);
  client.send({
    jsonrpc: "2.0",
    id: client.nextId++,
    method: "initialize",
    params: { processId: process.pid, rootUri: null, capabilities: {} },
  });
  client.send({ jsonrpc: "2.0", method: "initialized", params: {} });

  function openDocument(document) {
    if (document.languageId !== "sensepin") {
      return;
    }
    client.send({
      jsonrpc: "2.0",
      method: "textDocument/didOpen",
      params: {
        textDocument: {
          uri: document.uri.toString(),
          languageId: "sensepin",
          version: document.version,
          text: document.getText(),
        },
      },
    });
  }

  vscode.workspace.textDocuments.forEach(openDocument);
  context.subscriptions.push(vscode.workspace.onDidOpenTextDocument(openDocument));
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document.languageId !== "sensepin") {
        return;
      }
      client.send({
        jsonrpc: "2.0",
        method: "textDocument/didChange",
        params: {
          textDocument: { uri: event.document.uri.toString(), version: event.document.version },
          contentChanges: [{ text: event.document.getText() }],
        },
      });
    })
  );
  context.subscriptions.push({
    dispose() {
      if (client.proc) {
        client.send({ jsonrpc: "2.0", method: "exit" });
        client.proc.kill();
      }
    },
  });
}

function deactivate() {}

module.exports = { activate, deactivate };
