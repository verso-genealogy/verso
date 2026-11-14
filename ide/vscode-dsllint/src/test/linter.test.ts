import * as assert from "assert";
import { findLinterScript } from "../linter";

describe("findLinterScript", () => {
  it("returns null when no workspace folders", () => {
    assert.strictEqual(findLinterScript([]), null);
  });

  it("returns null when dsllint.py not in folder", () => {
    const folders = [{ uri: { fsPath: "/nonexistent/path" } }];
    assert.strictEqual(findLinterScript(folders), null);
  });

  it("finds dsllint.py in workspace root", () => {
    // A folder of its own holding a dsllint.py: the extension lives apart from any corpus.
    const fs = require("fs");
    const os = require("os");
    const path = require("path");
    const projectRoot = fs.mkdtempSync(path.join(os.tmpdir(), "dsllint-root-"));
    try {
      fs.writeFileSync(path.join(projectRoot, "dsllint.py"), "");
      const folders = [{ uri: { fsPath: "/nonexistent/path" } }, { uri: { fsPath: projectRoot } }];
      const result = findLinterScript(folders);
      assert.strictEqual(result, path.join(projectRoot, "dsllint.py"));
    } finally {
      fs.rmSync(projectRoot, { recursive: true, force: true });
    }
  });
});
