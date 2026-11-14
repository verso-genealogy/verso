import * as vscode from "vscode";
import { fixMap } from "./diagnostics";
import { findReplaceRange, findRemoveRange, findRemoveArgRange } from "./quickfixUtils";

export class DslLintQuickFixProvider implements vscode.CodeActionProvider {
  provideCodeActions(
    document: vscode.TextDocument,
    _range: vscode.Range,
    context: vscode.CodeActionContext
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    for (const diagnostic of context.diagnostics) {
      if (diagnostic.source !== "dsllint" || !diagnostic.code) continue;

      const fixKey = diagnostic.code as string;
      const fixData = fixMap.get(fixKey);
      if (!fixData) continue;

      const line = Math.max(0, (fixData.line || 1) - 1);
      if (line >= document.lineCount) continue;

      const lineText = document.lineAt(line).text;

      if (fixData.type === "replace_kwarg" && fixData.old && fixData.new) {
        const range = findReplaceRange(lineText, fixData.old, fixData.col);
        if (!range) continue;

        const replaceRange = new vscode.Range(line, range[0], line, range[1]);
        const action = new vscode.CodeAction(
          `Replace with ${fixData.new}`,
          vscode.CodeActionKind.QuickFix
        );
        action.edit = new vscode.WorkspaceEdit();
        action.edit.replace(document.uri, replaceRange, fixData.new);
        action.diagnostics = [diagnostic];
        action.isPreferred = true;
        actions.push(action);
      } else if (fixData.type === "remove_kwarg" && fixData.kwarg) {
        const range = findRemoveRange(lineText, fixData.kwarg, fixData.col);
        if (!range) continue;

        const removeRange = new vscode.Range(line, range[0], line, range[1]);
        const action = new vscode.CodeAction(
          `Remove redundant ${fixData.kwarg}`,
          vscode.CodeActionKind.QuickFix
        );
        const edit = new vscode.WorkspaceEdit();
        edit.delete(document.uri, removeRange);
        action.edit = edit;
        action.diagnostics = [diagnostic];
        action.isPreferred = true;
        actions.push(action);
      } else if (
        fixData.type === "remove_arg" &&
        fixData.col != null &&
        fixData.end_col != null
      ) {
        const range = findRemoveArgRange(lineText, fixData.col, fixData.end_col);
        const removeRange = new vscode.Range(line, range[0], line, range[1]);
        const action = new vscode.CodeAction(
          `Remove redundant ${fixData.kwarg ?? "argument"}`,
          vscode.CodeActionKind.QuickFix
        );
        const edit = new vscode.WorkspaceEdit();
        edit.delete(document.uri, removeRange);
        action.edit = edit;
        action.diagnostics = [diagnostic];
        action.isPreferred = true;
        actions.push(action);
      }
    }

    return actions;
  }
}
