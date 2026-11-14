import * as assert from "assert";
import { isDslFile } from "../fileDetection";

describe("isDslFile", () => {
  it("detects birth record files", () => {
    assert.strictEqual(isDslFile("zamanilovka_births_1790.py"), true);
  });

  it("detects marriage record files", () => {
    assert.strictEqual(isDslFile("zamanilovka_marriages_1791.py"), true);
  });

  it("detects death record files", () => {
    assert.strictEqual(isDslFile("nizhnyaya_yaichnitsa_deaths_1892.py"), true);
  });

  it("detects files with full paths", () => {
    assert.strictEqual(
      isDslFile("/some/path/Заманиловка/1790/zamanilovka_births_1790.py"),
      true
    );
  });

  it("rejects core module files", () => {
    assert.strictEqual(isDslFile("genealogy.py"), false);
    assert.strictEqual(isDslFile("births.py"), false);
    assert.strictEqual(isDslFile("statuses.py"), false);
  });

  it("rejects test files", () => {
    assert.strictEqual(isDslFile("test_births.py"), false);
    assert.strictEqual(isDslFile("test_genealogy.py"), false);
  });

  it("rejects non-Python files", () => {
    assert.strictEqual(isDslFile("births_1790.csv"), false);
  });

  it("rejects files without year", () => {
    assert.strictEqual(isDslFile("zamanilovka_births.py"), false);
  });

  it("detects census record files (with archive-suffix)", () => {
    // Горюхино census files use a trailing `_dXXXX...` archive suffix.
    assert.strictEqual(
      isDslFile("gorjuhino_census_1717_d1.py"),
      true,
    );
    assert.strictEqual(
      isDslFile("gorjuhino_census_1850_d2.py"),
      true,
    );
    assert.strictEqual(
      isDslFile("sobakevichevo_census_1816_d3_penochkin.py"),
      true,
    );
  });

  it("detects divorce record files", () => {
    assert.strictEqual(
      isDslFile("zamanilovka_divorces_1885.py"),
      true,
    );
  });

  it("detects external-source record files", () => {
    assert.strictEqual(
      isDslFile("gorjuhino_external_sources_1915.py"),
      true,
    );
    assert.strictEqual(
      isDslFile("nizhnyaya_yaichnitsa_external_sources_1914.py"),
      true,
    );
  });

  it("detects name-list record files", () => {
    assert.strictEqual(
      isDslFile("manilovka_name_lists_1917.py"),
      true,
    );
  });

  it("detects confession-list record files", () => {
    assert.strictEqual(
      isDslFile("zamanilovka_confessions_1828.py"),
      true,
    );
  });

  it("detects census files with full paths", () => {
    assert.strictEqual(
      isDslFile("/repo/Горюхино/1717/gorjuhino_census_1717_d1.py"),
      true,
    );
  });
});
