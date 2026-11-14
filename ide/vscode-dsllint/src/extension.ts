import * as vscode from "vscode";
import { isDslFile } from "./fileDetection";
import { mapResultsToDiagnostics } from "./diagnostics";
import { findLinterScript, runLinter } from "./linter";
import { DslLintQuickFixProvider } from "./quickfix";

let diagnosticCollection: vscode.DiagnosticCollection;

export function activate(context: vscode.ExtensionContext) {
  console.log("[dsllint] Extension activating...");

  diagnosticCollection =
    vscode.languages.createDiagnosticCollection("dsllint");
  context.subscriptions.push(diagnosticCollection);

  // Register Quick Fix provider
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      { scheme: "file", pattern: "**/*.py" },
      new DslLintQuickFixProvider(),
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );

  const linterScript = findLinterScript(
    vscode.workspace.workspaceFolders || []
  );
  console.log("[dsllint] Extension activated. Linter script:", linterScript);

  // Command: lint current file
  context.subscriptions.push(
    vscode.commands.registerCommand("dsllint.lint", () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        lintFile(editor.document);
      }
    })
  );

  // Command: lint all DSL files in workspace
  context.subscriptions.push(
    vscode.commands.registerCommand("dsllint.lintAll", async () => {
      const files = await vscode.workspace.findFiles(
        "**/*_{births,marriages,deaths}_*.py"
      );
      for (const file of files) {
        const doc = await vscode.workspace.openTextDocument(file);
        lintFile(doc);
      }
    })
  );

  // Auto-lint on save
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const config = vscode.workspace.getConfiguration("dsllint");
      if (config.get<boolean>("lintOnSave", true) && isDslFile(doc.fileName)) {
        lintFile(doc);
      }
    })
  );

  // Auto-lint on open
  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((doc) => {
      const config = vscode.workspace.getConfiguration("dsllint");
      if (config.get<boolean>("lintOnOpen", true) && isDslFile(doc.fileName)) {
        lintFile(doc);
      }
    })
  );

  // Clear diagnostics when file is closed
  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((doc) => {
      diagnosticCollection.delete(doc.uri);
    })
  );

  // Lint all already-open DSL files
  for (const doc of vscode.workspace.textDocuments) {
    if (isDslFile(doc.fileName)) {
      lintFile(doc);
    }
  }
}

function lintFile(doc: vscode.TextDocument): void {
  if (!isDslFile(doc.fileName)) {
    return;
  }

  const linterScript = findLinterScript(
    vscode.workspace.workspaceFolders || []
  );
  if (!linterScript) {
    return;
  }

  const config = vscode.workspace.getConfiguration("dsllint");
  const pythonPath = config.get<string>("pythonPath", "python3");

  runLinter(doc.uri.fsPath, pythonPath, linterScript).then((results) => {
    const diagnostics = mapResultsToDiagnostics(results, doc);
    diagnosticCollection.set(doc.uri, diagnostics);
  });
}

export function deactivate() {
  if (diagnosticCollection) {
    diagnosticCollection.dispose();
  }
}
