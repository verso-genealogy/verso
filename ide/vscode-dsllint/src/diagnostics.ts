import * as vscode from "vscode";
import { issueNarrowRange } from "./quickfixUtils";

export interface DslLintFix {
  type: "replace_kwarg" | "remove_kwarg" | "remove_arg";
  old?: string;
  new?: string;
  kwarg?: string;
  // For replace_kwarg/remove_kwarg: 0-based char column where the target
  // `kwarg=value` token starts (pins the occurrence on lines with several
  // matching kwargs). For remove_arg: the 0-based char column where the
  // positional argument begins.
  col?: number;
  // remove_arg only: 0-based char column just past the positional argument's
  // last char (its AST end offset, converted to a char column).
  end_col?: number;
}

export interface DslLintIssue {
  level: "error" | "warn";
  line: number;
  message: string;
  // What the finding is, in no language: its code (`CPL002`, `SLC001`), the message's
  // params (what the DSL wrote; a nested message is {key, params}) and the token it is about.
  // Absent in the output of a dsllint from before them.
  code?: string;
  params?: Record<string, unknown>;
  token?: string | null;
  // Optional issue-level highlight span (0-based char columns of the exact
  // flagged token, e.g. ULC001's string literal). Preferred over fix- or
  // message-derived ranges: it pins THIS occurrence when the same text
  // appears earlier on the line.
  col?: number;
  end_col?: number;
  fix?: DslLintFix;
}

export interface DslLintResult {
  file: string;
  linter: string;
  issues: DslLintIssue[];
}

/** Stores fix data keyed by a composite string, linked via diagnostic.code. */
export const fixMap = new Map<string, DslLintFix & { line: number }>();

/**
 * Map linter results to VS Code diagnostics.
 */
export function mapResultsToDiagnostics(
  results: DslLintResult[],
  doc: vscode.TextDocument
): vscode.Diagnostic[] {
  const diagnostics: vscode.Diagnostic[] = [];

  for (const result of results) {
    for (const issue of result.issues) {
      // Convert 1-based line to 0-based, clamp to valid range
      const line = Math.max(0, Math.min(issue.line - 1, doc.lineCount - 1));
      const lineText = doc.lineAt(line).text;
      // Narrow the highlight to the offending token when locatable; otherwise
      // fall back to the full line (structural / multi-line issues).
      const narrowed = issueNarrowRange(lineText, issue);
      const range = narrowed
        ? new vscode.Range(line, narrowed[0], line, narrowed[1])
        : doc.lineAt(line).range;

      const severity =
        issue.level === "error"
          ? vscode.DiagnosticSeverity.Error
          : vscode.DiagnosticSeverity.Warning;

      const diagnostic = new vscode.Diagnostic(
        range,
        `[${result.linter}] ${issue.message}`,
        severity
      );
      diagnostic.source = "dsllint";

      // Store fix metadata if available
      if (issue.fix) {
        const fixKey = `${issue.line}:${result.linter}:${issue.fix.type}`;
        fixMap.set(fixKey, { ...issue.fix, line: issue.line });
        diagnostic.code = fixKey;
      }

      diagnostics.push(diagnostic);
    }
  }

  return diagnostics;
}
