package com.genealogy.dsllint

import com.genealogy.dsllint.lint.DslLintParser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class DslLintParserTest {

    @Test fun emptyStringReturnsEmptyList() {
        assertTrue(DslLintParser.parse("").isEmpty())
        assertTrue(DslLintParser.parse("   ").isEmpty())
    }

    @Test fun malformedJsonReturnsEmptyList() {
        assertTrue(DslLintParser.parse("not json").isEmpty())
    }

    @Test fun parsesIssueWithoutFix() {
        val json = """
            [
              {
                "file": "/repo/k.py",
                "linter": "single_line_calls",
                "issues": [
                  {"level": "error", "line": 10, "message": "spans multiple lines"}
                ]
              }
            ]
        """.trimIndent()
        val results = DslLintParser.parse(json)
        assertEquals(1, results.size)
        val result = results[0]
        assertEquals("/repo/k.py", result.file)
        assertEquals("single_line_calls", result.linter)
        assertEquals(1, result.issues.size)
        val issue = result.issues[0]
        assertEquals("error", issue.level)
        assertEquals(10, issue.line)
        assertEquals("spans multiple lines", issue.message)
        assertNull(issue.fix)
    }

    @Test fun parsesReplaceKwargFix() {
        val json = """
            [{
              "file": "/repo/k.py",
              "linter": "single_line_calls",
              "issues": [{
                "level": "error", "line": 42,
                "message": "use MESHCHANIN",
                "fix": {"type": "replace_kwarg", "old": "\"мещанин\"", "new": "MESHCHANIN"}
              }]
            }]
        """.trimIndent()
        val results = DslLintParser.parse(json)
        val fix = results[0].issues[0].fix
        assertNotNull(fix)
        assertEquals("replace_kwarg", fix.type)
        assertEquals("\"мещанин\"", fix.old)
        assertEquals("MESHCHANIN", fix.new)
        assertNull(fix.kwarg)
    }

    @Test fun parsesRemoveKwargFix() {
        val json = """
            [{
              "file": "/repo/k.py",
              "linter": "single_line_calls",
              "issues": [{
                "level": "error", "line": 55,
                "message": "redundant residence",
                "fix": {"type": "remove_kwarg", "kwarg": "residence"}
              }]
            }]
        """.trimIndent()
        val results = DslLintParser.parse(json)
        val fix = results[0].issues[0].fix
        assertNotNull(fix)
        assertEquals("remove_kwarg", fix.type)
        assertEquals("residence", fix.kwarg)
        assertNull(fix.old)
        assertNull(fix.new)
    }

    @Test fun parsesCensusBirthMonthReplaceKwargFix() {
        // BMC001: integer birth_month= → Month constant. Advisory (warn) with a
        // col-pinned replace_kwarg fix; routes to ReplaceKwargFix in the annotator.
        val json = """
            [{
              "file": "/repo/census.py",
              "linter": "census_birth_month",
              "issues": [{
                "level": "warn", "line": 23,
                "message": "use Month.OCTOBER instead of integer literal birth_month=10",
                "fix": {"type": "replace_kwarg", "old": "10", "new": "Month.OCTOBER", "col": 83}
              }]
            }]
        """.trimIndent()
        val results = DslLintParser.parse(json)
        assertEquals("census_birth_month", results[0].linter)
        val issue = results[0].issues[0]
        assertEquals("warn", issue.level)
        val fix = issue.fix
        assertNotNull(fix)
        assertEquals("replace_kwarg", fix.type)
        assertEquals("10", fix.old)
        assertEquals("Month.OCTOBER", fix.new)
        assertEquals(83, fix.col)
    }

    @Test fun parsesIssueLevelColumns() {
        // ULC001-style issues carry col/end_col on the ISSUE (no fix): the
        // exact char span of the flagged string literal, so the annotator
        // highlights the right occurrence when the same value appears
        // earlier on the line (e.g. inside departure_reason prose).
        val json = """
            [{
              "file": "/repo/census.py",
              "linter": "unmapped_location",
              "issues": [{
                "level": "warn", "line": 7,
                "message": "[ULC001] unmapped destination 'Лесные Лопухи'",
                "col": 120, "end_col": 134
              }]
            }]
        """.trimIndent()
        val issue = DslLintParser.parse(json)[0].issues[0]
        assertEquals(120, issue.col)
        assertEquals(134, issue.end_col)
        assertNull(issue.fix)
    }

    @Test fun parsesMultipleLinters() {
        val json = """
            [
              {"file": "/repo/k.py", "linter": "single_line_calls", "issues": [
                {"level": "error", "line": 1, "message": "a"}
              ]},
              {"file": "/repo/k.py", "linter": "genders", "issues": [
                {"level": "warn", "line": 20, "message": "b"}
              ]}
            ]
        """.trimIndent()
        val results = DslLintParser.parse(json)
        assertEquals(2, results.size)
        assertEquals("single_line_calls", results[0].linter)
        assertEquals("genders", results[1].linter)
        assertEquals("warn", results[1].issues[0].level)
    }

    @Test fun parsesCodeParamsAndToken() {
        val json = """
            [{"file": "/repo/k.py", "linter": "unmapped_location", "issues": [{
              "level": "warn", "line": 3, "message": "[ULC001] место жительства: «Новая» нет среди мест корпуса",
              "code": "ULC001", "params": {"place": "Новая"}, "token": "Новая", "col": 20, "end_col": 27}]}]
        """.trimIndent()
        val issue = DslLintParser.parse(json)[0].issues[0]
        assertEquals("ULC001", issue.code)
        assertEquals(mapOf("place" to "Новая"), issue.params)
        assertEquals("Новая", issue.token)
    }

    @Test fun parsesTheOutputOfAnOlderDsllint() {
        val json = """[{"file": "/repo/k.py", "linter": "genders", "issues": [{"level": "error", "line": 1, "message": "expected MALE"}]}]"""
        val issue = DslLintParser.parse(json)[0].issues[0]
        assertNull(issue.code)
        assertNull(issue.params)
        assertNull(issue.token)
    }
}
