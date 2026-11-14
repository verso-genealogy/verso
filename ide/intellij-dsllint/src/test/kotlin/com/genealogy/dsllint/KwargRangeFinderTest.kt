package com.genealogy.dsllint

import com.genealogy.dsllint.quickfix.KwargRangeFinder
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class KwargRangeFinderTest {

    @Test fun findReplaceRangeLocatesQuotedLiteral() {
        val line = "                             father=person(\"Петр\", \"Иванов\", status=\"мещанин\")),"
        val range = KwargRangeFinder.findReplaceRange(line, "\"мещанин\"")
        assertNotNull(range)
        assertEquals("\"мещанин\"", line.substring(range.first, range.last + 1))
    }

    @Test fun findReplaceRangeReturnsNullWhenAbsent() {
        val line = "    father=person(\"Петр\"),"
        assertNull(KwargRangeFinder.findReplaceRange(line, "\"мещанин\""))
    }

    @Test fun findRemoveRangeConsumesLeadingComma() {
        val line = "    father=person(\"Петр\", \"Иванов\", residence=\"V\"),"
        val range = KwargRangeFinder.findRemoveRange(line, "residence")
        assertNotNull(range)
        val removed = line.substring(range.first, range.last + 1)
        assertTrue(removed.contains("residence="), "removed: \"$removed\"")
        val remaining = line.substring(0, range.first) + line.substring(range.last + 1)
        assertTrue(remaining.contains("person(\"Петр\", \"Иванов\")"))
    }

    @Test fun findRemoveRangeConsumesTrailingCommaForFirstKwarg() {
        val line = "    birth(1, \"муж\", 1, 1, cause_of_death=\"натуральная\", child=person(\"Иван\")),"
        val range = KwargRangeFinder.findRemoveRange(line, "cause_of_death")
        assertNotNull(range)
        val remaining = line.substring(0, range.first) + line.substring(range.last + 1)
        assertTrue(!remaining.contains("cause_of_death"))
        assertTrue(!remaining.contains(",, "), "remaining: \"$remaining\"")
    }

    @Test fun findRemoveRangeReturnsNullWhenAbsent() {
        val line = "    father=person(\"Петр\"),"
        assertNull(KwargRangeFinder.findRemoveRange(line, "residence"))
    }

    @Test fun findRemoveRangeHandlesConstantValue() {
        val line = "    father=person(\"Петр\", status=ECON_PEASANT_MALE),"
        val range = KwargRangeFinder.findRemoveRange(line, "status")
        assertNotNull(range)
        val remaining = line.substring(0, range.first) + line.substring(range.last + 1)
        assertTrue(!remaining.contains("status="))
        assertTrue(remaining.contains("person(\"Петр\")"))
    }

    @Test fun findKwargRangeReturnsKwargWithoutSeparator() {
        val line = "    person(\"Анна\", status=\"YASAK_PEASANT_FEMALE\"),"
        val range = KwargRangeFinder.findKwargRange(line, "status")
        assertNotNull(range)
        assertEquals("status=\"YASAK_PEASANT_FEMALE\"", line.substring(range.first, range.last + 1))
    }

    @Test fun findKwargRangeWithConstantValue() {
        val line = "    person(\"Петр\", status=ECON_PEASANT_MALE),"
        val range = KwargRangeFinder.findKwargRange(line, "status")
        assertNotNull(range)
        assertEquals("status=ECON_PEASANT_MALE", line.substring(range.first, range.last + 1))
    }

    @Test fun findKwargRangeReturnsNullWhenAbsent() {
        val line = "    person(\"Петр\"),"
        assertNull(KwargRangeFinder.findKwargRange(line, "status"))
    }

    // --- positional arg removal (census person("Имя", "Отчество", "Фамилия")) ---

    @Test fun findRemoveArgRangeConsumesLeadingCommaForTrailingSurname() {
        val line = "        member(2, person(\"Марья\", \"Максимова\", \"Индюшева\"), CensusRole.WIFE, 36),"
        val start = line.indexOf("\"Индюшева\"")
        val end = start + "\"Индюшева\"".length
        val range = KwargRangeFinder.findRemoveArgRange(line, start, end)
        val remaining = line.substring(0, range.first) + line.substring(range.last + 1)
        assertTrue(remaining.contains("person(\"Марья\", \"Максимова\")"), "remaining: \"$remaining\"")
        assertTrue(!remaining.contains("\"Индюшева\""))
        assertTrue(!remaining.contains(",,"))
    }

    @Test fun findRemoveArgRangeRemovesTrailingPatronymic() {
        val line = "        member(2, person(\"Петр\", \"Васильев\"), CensusRole.SON, 19),"
        val start = line.indexOf("\"Васильев\"")
        val end = start + "\"Васильев\"".length
        val range = KwargRangeFinder.findRemoveArgRange(line, start, end)
        val remaining = line.substring(0, range.first) + line.substring(range.last + 1)
        assertTrue(remaining.contains("person(\"Петр\")"), "remaining: \"$remaining\"")
        assertTrue(!remaining.contains("\"Васильев\""))
    }

    // --- col-aware occurrence selection (lines with several status= kwargs) ---

    private val twoStatusLine =
        "    death(deceased=person(\"Иван\", status=YASAK_PEASANT_SON), " +
            "relative=person(\"Павел\", \"Григорьев\", status=YASAK_PEASANT_MALE)),"

    @Test fun findKwargRangeWithoutColHitsFirstOccurrence() {
        // Legacy behavior: first match — the deceased's SON (this was the bug).
        val range = KwargRangeFinder.findKwargRange(twoStatusLine, "status")
        assertNotNull(range)
        assertEquals("status=YASAK_PEASANT_SON", twoStatusLine.substring(range.first, range.last + 1))
    }

    @Test fun findKwargRangeWithColTargetsRelativeStatus() {
        val col = twoStatusLine.lastIndexOf("status=")
        val range = KwargRangeFinder.findKwargRange(twoStatusLine, "status", col)
        assertNotNull(range)
        assertEquals("status=YASAK_PEASANT_MALE", twoStatusLine.substring(range.first, range.last + 1))
    }

    @Test fun findRemoveRangeWithColRemovesRelativeNotDeceased() {
        val col = twoStatusLine.lastIndexOf("status=")
        val range = KwargRangeFinder.findRemoveRange(twoStatusLine, "status", col)
        assertNotNull(range)
        val remaining = twoStatusLine.substring(0, range.first) + twoStatusLine.substring(range.last + 1)
        assertTrue(remaining.contains("status=YASAK_PEASANT_SON"), "deceased status must survive")
        assertTrue(!remaining.contains("status=YASAK_PEASANT_MALE"), "relative status must be removed")
    }

    @Test fun findReplaceRangeWithColTargetsSecondLiteral() {
        val line = "    person(status=\"X\"), person(status=\"X\")"
        val col = line.lastIndexOf("status=")
        val range = KwargRangeFinder.findReplaceRange(line, "\"X\"", col)
        assertNotNull(range)
        assertTrue(range.first > line.indexOf("\"X\""), "should target the second literal, not the first")
    }

    // --- BMC001 census birth_month integer → Month constant ---
    // The bare-integer `old` ("5") also appears in the age ("25") earlier on the
    // line, so the fix only resolves correctly because it carries the col of
    // `birth_month`. This guards the integer→Month constant quick-fix.
    @Test fun findReplaceRangeWithColTargetsBirthMonthNotAge() {
        val line = "        member(2, person(\"Иван\"), CensusRole.SON, 25, birth_month=5, birth_year=1830),"
        val col = line.indexOf("birth_month")
        val range = KwargRangeFinder.findReplaceRange(line, "5", col)
        assertNotNull(range)
        assertEquals("5", line.substring(range.first, range.last + 1))
        val replaced = line.substring(0, range.first) + "Month.MAY" + line.substring(range.last + 1)
        assertTrue(replaced.contains("birth_month=Month.MAY"), "replaced: \"$replaced\"")
        assertTrue(replaced.contains("SON, 25,"), "the age must be untouched")
    }

    // --- genders mother=/father= role swap ---
    // Here `old` is the kwarg NAME itself ("mother="), not a value. The same
    // record may carry several `person(` arguments, so the fix's col is what
    // keeps the swap on the flagged one.
    @Test fun findReplaceRangeSwapsParentKwargName() {
        val line = "        birth(7, Gender.MALE, 3, 4, child=person(\"Пётръ\"), " +
            "mother=person(\"Иванъ\", \"Видоплясовъ\")),"
        val col = line.indexOf("mother=")
        val range = KwargRangeFinder.findReplaceRange(line, "mother=", col)
        assertNotNull(range)
        val replaced = line.substring(0, range.first) + "father=" + line.substring(range.last + 1)
        assertTrue(replaced.contains("father=person(\"Иванъ\""), "replaced: \"$replaced\"")
        assertTrue(replaced.contains("child=person(\"Пётръ\")"), "the child must be untouched")
    }

    @Test fun findMessageTokenRangePrefersSourceFormFromMessage() {
        val line = "    child=person(\"Ерасъ\", \"Ивановъ\"),"
        val range = KwargRangeFinder.findMessageTokenRange(line, "Unknown first name 'Ерас' (from 'Ерасъ')")
        assertNotNull(range)
        assertEquals("Ерасъ", line.substring(range.first, range.last + 1))
    }

    @Test fun findMessageTokenRangeFallsBackToFirstQuotedToken() {
        val line = "    person(\"Петръ\", residence=\"Заманиловка\"),"
        val range = KwargRangeFinder.findMessageTokenRange(line, "non-Cyrillic characters in name 'Петръ'")
        assertNotNull(range)
        assertEquals("Петръ", line.substring(range.first, range.last + 1))
    }

    @Test fun findMessageTokenRangeReturnsNullWhenTokenNotOnLine() {
        val line = "    person(\"Иванъ\"),"
        assertNull(KwargRangeFinder.findMessageTokenRange(line, "Unknown first name 'Ерас' (from 'Ерасъ')"))
    }

    @Test fun findMessageTokenRangeReturnsNullWhenNoQuotedToken() {
        val line = "    person(\"Иванъ\"),"
        assertNull(KwargRangeFinder.findMessageTokenRange(line, "name() spans lines 3-5"))
    }

    @Test fun findMessageTokenRangeNarrowsGuillemetPatronymic() {
        val line = "    person(\"Иванъ\", \"Ивановичъ\", residence=\"Горюхино\", status=PEASANT_MALE),"
        val message = "[PAF001] full patronymic «Ивановичъ» on a non-high-rank person — " +
            "the full «-вич» form was a privilege of nobility/officers/clergy; " +
            "peasants used the short полуотчество («Абрамовъ»). Keep it only if " +
            "the source records it (e.g. a gwar WWI card)."
        val range = KwargRangeFinder.findMessageTokenRange(line, message)
        assertNotNull(range)
        assertEquals("Ивановичъ", line.substring(range.first, range.last + 1))
    }

    @Test fun findMessageTokenRangeNarrowsDoubleQuotedRelationshipRef() {
        val line = "        relatives=[relative(person(\"Иван\", \"Ильин\"), Relationship.HUSBAND, \"восприемник №2\")]),"
        val message = "relationship_ref=\"восприемник №2\" is not allowed; use one of: " +
            "\"восприемница\", \"жених\", \"мать\", \"невеста\", or \"восприемника №N\""
        val range = KwargRangeFinder.findMessageTokenRange(line, message)
        assertNotNull(range)
        assertEquals("\"восприемник №2\"", line.substring(range.first, range.last + 1))
    }

    @Test fun findMessageTokenRangeSkipsExpectedHostsNotOnLine() {
        // ESC001: the expected hosts are quoted before the actual URL, but they
        // are not on the line; the narrow target is the offending URL that is.
        val line = "        source_url=\"https://gwar.mil.ru/x\","
        val message = "[external_sources] ESC001 source_url host should contain " +
            "'familio.org/catalogs/vss' or 'viewer.rsl.ru' for criminal_record(); " +
            "got 'https://gwar.mil.ru/x'"
        val range = KwargRangeFinder.findMessageTokenRange(line, message)
        assertNotNull(range)
        assertEquals("https://gwar.mil.ru/x", line.substring(range.first, range.last + 1))
    }

    @Test fun findTokenRangeFindsTheIssueTokenWhateverTheMessageSays() {
        // The token is what the finding is about, in no language; the message may quote nothing.
        val line = "        destination=\"Лесные Лопухи\")"
        val range = KwargRangeFinder.findTokenRange(line, "Лесные Лопухи")
        assertNotNull(range)
        assertEquals("Лесные Лопухи", line.substring(range.first, range.last + 1))
        assertNull(KwargRangeFinder.findTokenRange(line, "Едва Жива"))
        assertNull(KwargRangeFinder.findTokenRange(line, null))
        assertNull(KwargRangeFinder.findTokenRange(line, ""))
    }

    @Test fun findTokenRangePrefersAWholeWord() {
        val line = "father=person(\"Иванъ\", \"Ивановъ\"), child=person(\"Иван\")"
        val at = line.lastIndexOf("\"Иван\"") + 1
        assertEquals(at until at + 4, KwargRangeFinder.findTokenRange(line, "Иван"))
        assertEquals(8 until 12, KwargRangeFinder.findTokenRange("person(\"Ивановъ\")", "Иван"))
    }
}
