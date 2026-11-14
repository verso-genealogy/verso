import * as cp from "child_process";
import * as path from "path";
import { DslLintResult } from "./diagnostics";

/**
 * Find dsllint.py in the workspace.
 */
export function findLinterScript(
  workspaceFolders: readonly { uri: { fsPath: string } }[]
): string | null {
  for (const folder of workspaceFolders) {
    const candidate = path.join(folder.uri.fsPath, "dsllint.py");
    try {
      require("fs").accessSync(candidate);
      return candidate;
    } catch {
      // not found in this folder
    }
  }
  return null;
}

/**
 * Run dsllint.py --json on a file and return structured results.
 */
export function runLinter(
  filePath: string,
  pythonPath: string,
  linterScript: string
): Promise<DslLintResult[]> {
  return new Promise((resolve) => {
    const proc = cp.spawn(
      pythonPath,
      [linterScript, "--json", filePath],
      {
        cwd: path.dirname(linterScript),
        timeout: 30000,
      }
    );

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data: Buffer) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    proc.on("close", () => {
      if (!stdout.trim()) {
        resolve([]);
        return;
      }

      try {
        const results: DslLintResult[] = JSON.parse(stdout);
        resolve(results);
      } catch (e) {
        console.error("dsllint: failed to parse JSON output:", e);
        if (stderr) {
          console.error("dsllint stderr:", stderr);
        }
        resolve([]);
      }
    });

    proc.on("error", (err: Error) => {
      console.error("dsllint: failed to spawn linter:", err.message);
      resolve([]);
    });
  });
}
