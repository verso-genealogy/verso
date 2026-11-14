import * as assert from "assert";
import * as fs from "fs";
import * as path from "path";

/**
 * The TextMate injection grammar is data, not code — nothing type-checks it, and
 * a record family whose verbs are missing from `dsl-function-calls` simply goes
 * unhighlighted with no error anywhere. Read the shipped file and exercise the
 * pattern the way the editor does.
 *
 * The IntelliJ port of these same regexes is covered by
 * `intellij-dsllint/src/test/kotlin/com/genealogy/dsllint/highlight/DslSyntaxAnnotatorTest.kt`.
 */
const GRAMMAR_PATH = path.join(
  __dirname,
  "../../syntaxes/genealogy-dsl.injection.tmLanguage.json",
);

interface Grammar {
  repository: Record<string, { match: string }>;
}

function pattern(rule: string): RegExp {
  const grammar: Grammar = JSON.parse(fs.readFileSync(GRAMMAR_PATH, "utf8"));
  return new RegExp(grammar.repository[rule].match);
}

describe("tmLanguage dsl-function-calls", () => {
  const matches = (source: string) => pattern("dsl-function-calls").test(source);

  it("highlights name-list record verbs", () => {
    assert.strictEqual(matches('name_list_records("ГАТО", "R-5328", ...)'), true);
    assert.strictEqual(matches("listed_person(1, person(...))"), true);
  });

  it("still highlights the metric-book verbs", () => {
    assert.strictEqual(matches("person("), true);
    assert.strictEqual(matches("birth_records("), true);
    assert.strictEqual(matches("marriage_month_year("), true);
  });

  it("requires a call, not a bare mention", () => {
    assert.strictEqual(matches("# listed_person is the name-list verb"), false);
    assert.strictEqual(matches("from x import name_list_records"), false);
  });

  it("does not highlight `person` inside `listed_person`", () => {
    // `person` precedes `listed_person` in the alternation, so a word boundary
    // is the only thing keeping it from matching the tail of the longer verb.
    const re = pattern("dsl-function-calls");
    const m = re.exec("listed_person(1, ...)");
    assert.strictEqual(m?.[0], "listed_person");
    assert.strictEqual(m?.index, 0);
  });
});
