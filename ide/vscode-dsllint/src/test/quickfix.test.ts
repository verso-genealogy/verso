import * as assert from "assert";
import {
  findReplaceRange,
  findRemoveRange,
  findRemoveArgRange,
  findKwargRange,
  findMessageTokenRange,
  narrowRange,
} from "../quickfixUtils";

describe("findReplaceRange", () => {
  it("finds a quoted string literal on a line", () => {
    const line = '                             father=person("Петр", "Иванов", status="мещанин")),';
    const result = findReplaceRange(line, '"мещанин"');
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), '"мещанин"');
  });

  it("returns null when not found", () => {
    const line = '    father=person("Петр"),';
    assert.strictEqual(findReplaceRange(line, '"мещанин"'), null);
  });
});

describe("findRemoveRange", () => {
  it("removes kwarg with leading comma-space", () => {
    //                                       should remove: ", residence="V""
    const line = '    father=person("Петр", "Иванов", residence="V"),';
    const result = findRemoveRange(line, "residence");
    assert.ok(result !== null);
    const removed = line.substring(result![0], result![1]);
    assert.ok(removed.includes("residence="), `removed: "${removed}"`);
    // The remaining line should be valid Python
    const remaining = line.substring(0, result![0]) + line.substring(result![1]);
    assert.ok(remaining.includes('person("Петр", "Иванов")'));
  });

  it("removes kwarg with trailing comma-space when first kwarg", () => {
    const line = '    birth(1, "муж", 1, 1, cause_of_death="натуральная", child=person("Иван")),';
    const result = findRemoveRange(line, "cause_of_death");
    assert.ok(result !== null);
    const remaining = line.substring(0, result![0]) + line.substring(result![1]);
    assert.ok(!remaining.includes("cause_of_death"));
    // Should not leave double commas or leading comma
    assert.ok(!remaining.includes(",, "), `remaining: "${remaining}"`);
  });

  it("returns null when kwarg not found", () => {
    const line = '    father=person("Петр"),';
    assert.strictEqual(findRemoveRange(line, "residence"), null);
  });

  it("handles kwarg with constant value", () => {
    const line = '    father=person("Петр", status=ECON_PEASANT_MALE),';
    const result = findRemoveRange(line, "status");
    assert.ok(result !== null);
    const remaining = line.substring(0, result![0]) + line.substring(result![1]);
    assert.ok(!remaining.includes("status="));
    assert.ok(remaining.includes('person("Петр")'));
  });
});

describe("findRemoveArgRange", () => {
  it("removes a trailing positional surname with its leading comma", () => {
    // census member: person("Марья", "Максимова", "Индюшева")
    const line = '        member(2, person("Марья", "Максимова", "Индюшева"), CensusRole.WIFE, 36),';
    const start = line.indexOf('"Индюшева"');
    const end = start + '"Индюшева"'.length;
    const [s, e] = findRemoveArgRange(line, start, end);
    const remaining = line.substring(0, s) + line.substring(e);
    assert.ok(remaining.includes('person("Марья", "Максимова")'), `remaining: "${remaining}"`);
    assert.ok(!remaining.includes('"Индюшева"'));
    assert.ok(!remaining.includes(",,"));
  });

  it("removes a trailing positional patronymic with its leading comma", () => {
    // after the surname is gone: person("Петр", "Васильев")
    const line = '        member(2, person("Петр", "Васильев"), CensusRole.SON, 19),';
    const start = line.indexOf('"Васильев"');
    const end = start + '"Васильев"'.length;
    const [s, e] = findRemoveArgRange(line, start, end);
    const remaining = line.substring(0, s) + line.substring(e);
    assert.ok(remaining.includes('person("Петр")'), `remaining: "${remaining}"`);
    assert.ok(!remaining.includes('"Васильев"'));
  });
});

describe("findKwargRange", () => {
  it("returns kwarg=value without surrounding separator (quoted value)", () => {
    const line = '    person("Анна", status="YASAK_PEASANT_FEMALE"),';
    const result = findKwargRange(line, "status");
    assert.ok(result !== null);
    assert.strictEqual(
      line.substring(result![0], result![1]),
      'status="YASAK_PEASANT_FEMALE"'
    );
  });

  it("returns kwarg=value with a constant value", () => {
    const line = '    person("Петр", status=ECON_PEASANT_MALE),';
    const result = findKwargRange(line, "status");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), "status=ECON_PEASANT_MALE");
  });

  it("returns null when kwarg absent", () => {
    const line = '    person("Петр"),';
    assert.strictEqual(findKwargRange(line, "status"), null);
  });
});

describe("col-aware occurrence selection", () => {
  // A single death() line with two status= kwargs: deceased's (not redundant)
  // and relative's (redundant). Cyrillic exercises byte→char column alignment.
  const twoStatus =
    '    death(deceased=person("Иван", status=YASAK_PEASANT_SON), ' +
    'relative=person("Павел", "Григорьев", status=YASAK_PEASANT_MALE)),';

  it("findKwargRange without col hits the first occurrence (legacy)", () => {
    const r = findKwargRange(twoStatus, "status");
    assert.ok(r !== null);
    assert.strictEqual(twoStatus.substring(r![0], r![1]), "status=YASAK_PEASANT_SON");
  });

  it("findKwargRange with col targets the relative's status", () => {
    const col = twoStatus.lastIndexOf("status=");
    const r = findKwargRange(twoStatus, "status", col);
    assert.ok(r !== null);
    assert.strictEqual(twoStatus.substring(r![0], r![1]), "status=YASAK_PEASANT_MALE");
  });

  it("findRemoveRange with col removes the relative's status, not the deceased's", () => {
    const col = twoStatus.lastIndexOf("status=");
    const r = findRemoveRange(twoStatus, "status", col);
    assert.ok(r !== null);
    const remaining = twoStatus.substring(0, r![0]) + twoStatus.substring(r![1]);
    assert.ok(remaining.includes("status=YASAK_PEASANT_SON"), "deceased status must survive");
    assert.ok(!remaining.includes("status=YASAK_PEASANT_MALE"), "relative status must be removed");
  });

  it("findReplaceRange with col targets the second literal", () => {
    const line = '    person(status="X"), person(status="X")';
    const col = line.lastIndexOf("status=");
    const r = findReplaceRange(line, '"X"', col);
    assert.ok(r !== null);
    assert.ok(r![0] > line.indexOf('"X"'), "should target the second literal");
  });
});

describe("BMC001 census birth_month replace_kwarg", () => {
  // age 25 contains a stray "5" BEFORE birth_month=5, so the bare-integer
  // `old` only resolves correctly because the fix carries `col` (the char
  // column of `birth_month`). This guards the integer→Month constant quick-fix.
  const line =
    '        member(2, person("Иван"), CensusRole.SON, 25, birth_month=5, birth_year=1830),';

  it("targets the birth_month value, not the stray 5 in the age", () => {
    const col = line.indexOf("birth_month");
    const result = narrowRange(
      line,
      { type: "replace_kwarg", old: "5", new: "Month.MAY", col },
      ""
    );
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), "5");
    // The replacement lands on birth_month, producing a valid Month constant.
    const replaced = line.substring(0, result![0]) + "Month.MAY" + line.substring(result![1]);
    assert.ok(replaced.includes("birth_month=Month.MAY"), replaced);
    assert.ok(replaced.includes("SON, 25,"), "the age must be untouched");
  });
});

describe("CSR001 census redundant status remove_kwarg", () => {
  // A census member whose explicit status repeats the RecordDefaults default.
  // Cyrillic before `status=` exercises the byte→char col conversion the linter
  // emits, and the member's `age` string here contains no stray token — but the
  // col still pins the exact kwarg on the (single) occurrence.
  const line =
    '        member(1, person("Иванъ", status=KAZ_MALE), CensusRole.HEAD, 45),';

  it("narrows the highlight to the status= kwarg via col", () => {
    const col = line.indexOf("status=");
    const result = narrowRange(line, { type: "remove_kwarg", kwarg: "status", col }, "");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), "status=KAZ_MALE");
  });

  it("removal leaves valid Python (member inherits the default)", () => {
    const col = line.indexOf("status=");
    const [s, e] = findRemoveRange(line, "status", col)!;
    const remaining = line.substring(0, s) + line.substring(e);
    assert.ok(!remaining.includes("status="));
    assert.ok(remaining.includes('person("Иванъ")'), `remaining: "${remaining}"`);
    assert.ok(!remaining.includes(",,"));
  });
});

describe("findMessageTokenRange", () => {
  it("prefers the (from '...') source form", () => {
    const line = '    child=person("Ерасъ", "Ивановъ"),';
    const result = findMessageTokenRange(line, "Unknown first name 'Ерас' (from 'Ерасъ')");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), "Ерасъ");
  });

  it("falls back to the first single-quoted token", () => {
    const line = '    person("Петръ", residence="Заманиловка"),';
    const result = findMessageTokenRange(line, "non-Cyrillic characters in name 'Петръ'");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), "Петръ");
  });

  it("narrows a double-quoted relationship_ref token (no fix)", () => {
    const line =
      '        relatives=[relative(person("Иван", "Ильин"), Relationship.HUSBAND, "восприемник №2")]),';
    const message =
      'relationship_ref="восприемник №2" is not allowed; use one of: ' +
      '"восприемница", "жених", "мать", "невеста", or "восприемника №N"';
    const result = findMessageTokenRange(line, message);
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), '"восприемник №2"');
  });

  it("narrows a guillemet-quoted patronymic (PAF001, no fix)", () => {
    const line =
      '    person("Иванъ", "Ивановичъ", residence="Горюхино", status=PEASANT_MALE),';
    const message =
      "[PAF001] full patronymic «Ивановичъ» on a non-high-rank person — " +
      "the full «-вич» form was a privilege of nobility/officers/clergy; " +
      "peasants used the short полуотчество («Абрамовъ»). Keep it only if " +
      "the source records it (e.g. a gwar WWI card).";
    const result = findMessageTokenRange(line, message);
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), "Ивановичъ");
  });

  it("narrows to the actual URL, skipping expected hosts not on the line (ESC001)", () => {
    const line = '        source_url="https://gwar.mil.ru/x",';
    const message =
      "[external_sources] ESC001 source_url host should contain " +
      "'familio.org/catalogs/vss' or 'viewer.rsl.ru' for criminal_record(); " +
      "got 'https://gwar.mil.ru/x'";
    const result = findMessageTokenRange(line, message);
    assert.ok(result !== null);
    // The expected hosts ('familio.org/catalogs/vss', 'viewer.rsl.ru') are not on
    // the line; the narrow target is the offending URL that is.
    assert.strictEqual(line.substring(result![0], result![1]), "https://gwar.mil.ru/x");
  });

  it("returns null when token not on the line", () => {
    const line = '    person("Иванъ"),';
    assert.strictEqual(
      findMessageTokenRange(line, "Unknown first name 'Ерас' (from 'Ерасъ')"),
      null
    );
  });

  it("returns null when message has no quoted token", () => {
    const line = '    person("Иванъ"),';
    assert.strictEqual(findMessageTokenRange(line, "name() spans lines 3-5"), null);
  });
});

describe("narrowRange", () => {
  it("uses fix.old for replace_kwarg", () => {
    const line = '    father=person("Петр", status="мещанин")),';
    const result = narrowRange(line, { type: "replace_kwarg", old: '"мещанин"', new: "MESHCHANIN" }, "");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), '"мещанин"');
  });

  it("uses fix.kwarg for remove_kwarg (no separator)", () => {
    const line = '    father=person("Петр", "Иванов", residence="V"),';
    const result = narrowRange(line, { type: "remove_kwarg", kwarg: "residence" }, "");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), 'residence="V"');
  });

  it("highlights just the positional arg for remove_arg", () => {
    const line = '        member(2, person("Марья", "Максимова", "Индюшева"), CensusRole.WIFE, 36),';
    const col = line.indexOf('"Индюшева"');
    const endCol = col + '"Индюшева"'.length;
    const result = narrowRange(line, { type: "remove_arg", kwarg: "last_name", col, end_col: endCol }, "");
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), '"Индюшева"');
  });

  it("falls back to the message token when no fix", () => {
    const line =
      '        relatives=[relative(person("Иван", "Ильин"), Relationship.HUSBAND, "восприемник №2")]),';
    const message = 'relationship_ref="восприемник №2" is not allowed; use one of: "невеста"';
    const result = narrowRange(line, undefined, message);
    assert.ok(result !== null);
    assert.strictEqual(line.substring(result![0], result![1]), '"восприемник №2"');
  });

  it("returns null when nothing can be located", () => {
    const line = '    person("Иванъ"),';
    assert.strictEqual(narrowRange(line, undefined, "name() spans lines 3-5"), null);
  });
});

describe("issueNarrowRange (issue-level col/end_col)", () => {
  const { issueNarrowRange } = require("../quickfixUtils");
  const line =
    'member(1, person("Иванъ"), CensusRole.HEAD, ' +
    'departure_reason="переведён в деревню Лесные Лопухи", ' +
    'destination="Лесные Лопухи")';

  it("prefers issue col span over the message-token fallback", () => {
    const col = line.lastIndexOf('"Лесные Лопухи"');
    const range = issueNarrowRange(line, {
      col,
      end_col: col + '"Лесные Лопухи"'.length,
      message: "[ULC001] unmapped destination 'Лесные Лопухи'",
    });
    assert.deepStrictEqual(range, [col, col + '"Лесные Лопухи"'.length]);
    // and NOT the first occurrence inside departure_reason
    assert.ok(range![0] > line.indexOf("Лесные Лопухи"));
  });

  it("finds the issue's token before the message's quotes", () => {
    // The message names no quoted token (another language, or a reworded one): the token does.
    const range = issueNarrowRange(line, {
      message: "[ULC001] the destination is not among the corpus's places",
      token: "Лесные Лопухи",
    });
    assert.deepStrictEqual(range, [line.indexOf("Лесные Лопухи"), line.indexOf("Лесные Лопухи") + 13]);
  });

  it("findTokenRange prefers the token as a whole word", () => {
    const { findTokenRange } = require("../quickfixUtils");
    const named = 'father=person("Иванъ", "Ивановъ"), child=person("Иван")';
    const at = named.lastIndexOf('"Иван"') + 1;
    assert.deepStrictEqual(findTokenRange(named, "Иван"), [at, at + 4]);
    // with no whole word on the line, the first occurrence stands
    assert.deepStrictEqual(findTokenRange('person("Ивановъ")', "Иван"), [8, 12]);
  });

  it("findTokenRange is null for a token not on the line", () => {
    const { findTokenRange } = require("../quickfixUtils");
    assert.strictEqual(findTokenRange(line, "Едва Жива"), null);
    assert.strictEqual(findTokenRange(line, ""), null);
  });

  it("falls back to message token search without cols", () => {
    const range = issueNarrowRange(line, {
      message: "[ULC001] unmapped destination 'Лесные Лопухи'",
    });
    assert.ok(range);
    assert.strictEqual(range![0], line.indexOf("Лесные Лопухи"));
  });
});

describe("genders mother=/father= role swap", () => {
  // A male name in the `mother=` slot. Here the fix's `old` is the kwarg NAME
  // itself ("mother="), not a value, and the record carries a second `person(`
  // argument — so the fix's col is what keeps the swap on the flagged one.
  const line =
    '        birth(7, Gender.MALE, 3, 4, child=person("Пётръ"), ' +
    'mother=person("Иванъ", "Видоплясовъ")),';
  const col = line.indexOf("mother=");

  it("swaps the flagged parent kwarg, leaving the other argument alone", () => {
    const range = narrowRange(
      line,
      { type: "replace_kwarg", old: "mother=", new: "father=", col },
      ""
    );
    assert.ok(range !== null);
    const replaced = line.substring(0, range![0]) + "father=" + line.substring(range![1]);
    assert.ok(replaced.includes('father=person("Иванъ"'), replaced);
    assert.ok(replaced.includes('child=person("Пётръ")'), "the child must be untouched");
  });

  it("highlights the whole argument, not just the kwarg the fix targets", () => {
    const { issueNarrowRange } = require("../quickfixUtils");
    const endCol = line.indexOf(")),") + 1;
    const range = issueNarrowRange(line, {
      col,
      end_col: endCol,
      fix: { type: "replace_kwarg", old: "mother=", new: "father=", col },
      message: "expected FEMALE for mother, got MALE",
    });
    assert.deepStrictEqual(range, [col, endCol]);
    assert.strictEqual(line.substring(range![0], range![1]), 'mother=person("Иванъ", "Видоплясовъ")');
  });
});
