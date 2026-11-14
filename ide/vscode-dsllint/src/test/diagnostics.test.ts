import * as assert from "assert";
import { DslLintResult, DslLintIssue } from "../diagnostics";

// We test the pure logic without VS Code API by verifying the data transformation.
// The actual mapResultsToDiagnostics needs VS Code runtime, so we test the data shape here.

describe("DslLintResult data shape", () => {
  it("empty results produce no issues", () => {
    const results: DslLintResult[] = [
      { file: "test.py", linter: "single_line_calls", issues: [] },
      { file: "test.py", linter: "genders", issues: [] },
      { file: "test.py", linter: "names", issues: [] },
    ];
    const totalIssues = results.reduce((n, r) => n + r.issues.length, 0);
    assert.strictEqual(totalIssues, 0);
  });

  it("issues have required fields", () => {
    const result: DslLintResult = {
      file: "test.py",
      linter: "genders",
      issues: [{ level: "error", line: 42, message: "expected MALE for groom" }],
    };
    assert.strictEqual(result.issues[0].level, "error");
    assert.strictEqual(result.issues[0].line, 42);
    assert.ok(result.issues[0].message.length > 0);
  });

  it("linter name is included in result", () => {
    const result: DslLintResult = {
      file: "test.py",
      linter: "names",
      issues: [{ level: "error", line: 1, message: "Unknown name 'Xyz'" }],
    };
    const prefixed = `[${result.linter}] ${result.issues[0].message}`;
    assert.ok(prefixed.startsWith("[names]"));
  });

  it("multiple linters merge issues", () => {
    const results: DslLintResult[] = [
      {
        file: "test.py",
        linter: "single_line_calls",
        issues: [{ level: "error", line: 10, message: "multi-line person()" }],
      },
      {
        file: "test.py",
        linter: "genders",
        issues: [{ level: "error", line: 20, message: "gender mismatch" }],
      },
      { file: "test.py", linter: "names", issues: [] },
    ];
    const totalIssues = results.reduce((n, r) => n + r.issues.length, 0);
    assert.strictEqual(totalIssues, 2);
  });
});

describe("DslLintIssue fix metadata", () => {
  it("issue with fix has replace_kwarg data", () => {
    const issue: DslLintIssue = {
      level: "error",
      line: 42,
      message: 'use constant MESHCHANIN instead of string literal status="мещанин"',
      fix: { type: "replace_kwarg", old: '"мещанин"', new: "MESHCHANIN" },
    };
    assert.ok(issue.fix);
    assert.strictEqual(issue.fix!.type, "replace_kwarg");
    assert.strictEqual(issue.fix!.old, '"мещанин"');
    assert.strictEqual(issue.fix!.new, "MESHCHANIN");
  });

  it("issue with fix has remove_kwarg data", () => {
    const issue: DslLintIssue = {
      level: "error",
      line: 55,
      message: 'redundant residence="Заманиловка" (already in RecordDefaults)',
      fix: { type: "remove_kwarg", kwarg: "residence" },
    };
    assert.ok(issue.fix);
    assert.strictEqual(issue.fix!.type, "remove_kwarg");
    assert.strictEqual(issue.fix!.kwarg, "residence");
  });

  it("issue without fix has no fix field", () => {
    const issue: DslLintIssue = {
      level: "error",
      line: 10,
      message: "person() spans lines 10-14",
    };
    assert.strictEqual(issue.fix, undefined);
  });

  it("fix key format is line:linter:type", () => {
    const issue: DslLintIssue = {
      level: "error",
      line: 42,
      message: "test",
      fix: { type: "replace_kwarg", old: '"x"', new: "X" },
    };
    const fixKey = `${issue.line}:single_line_calls:${issue.fix!.type}`;
    assert.strictEqual(fixKey, "42:single_line_calls:replace_kwarg");
  });
});

describe("DslLintIssue code, params and token", () => {
  it("reads them from dsllint --json", () => {
    const results = JSON.parse(
      '[{"file":"t.py","linter":"unmapped_location","issues":[{"level":"warn","line":3,' +
        '"message":"[ULC001] место жительства: «Новая» нет среди мест корпуса","code":"ULC001",' +
        '"params":{"place":"Новая"},"token":"Новая","col":20,"end_col":27}]}]',
    ) as DslLintResult[];
    const issue: DslLintIssue = results[0].issues[0];
    assert.strictEqual(issue.code, "ULC001");
    assert.deepStrictEqual(issue.params, { place: "Новая" });
    assert.strictEqual(issue.token, "Новая");
  });

  it("reads the output of a dsllint from before them", () => {
    const results = JSON.parse(
      '[{"file":"t.py","linter":"genders","issues":[{"level":"error","line":1,"message":"expected MALE"}]}]',
    ) as DslLintResult[];
    const issue = results[0].issues[0];
    assert.strictEqual(issue.code, undefined);
    assert.strictEqual(issue.token, undefined);
  });
});
