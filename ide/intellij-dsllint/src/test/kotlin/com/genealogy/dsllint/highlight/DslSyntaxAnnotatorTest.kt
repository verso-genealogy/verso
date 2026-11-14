package com.genealogy.dsllint.highlight

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * [DslSyntaxAnnotator]'s regexes are a hand-kept port of vscode-dsllint's
 * TextMate grammar (`syntaxes/genealogy-dsl.injection.tmLanguage.json`). Neither
 * side can see the other, so a record family added to one and forgotten in the
 * other just goes unhighlighted in that IDE with no error anywhere. The sibling
 * test is `vscode-dsllint/src/test/syntax.test.ts` — keep the two in step.
 */
class DslSyntaxAnnotatorTest {

    private fun matches(source: String) =
        DslSyntaxAnnotator.DSL_FUNCTIONS.containsMatchIn(source)

    @Test fun highlightsNameListVerbs() {
        assertTrue(matches("""name_list_records("ГАТО", "R-5328", ...)"""))
        assertTrue(matches("listed_person(1, person(...))"))
    }

    @Test fun highlightsMetricBookVerbs() {
        assertTrue(matches("person("))
        assertTrue(matches("birth_records("))
        assertTrue(matches("marriage_month_year("))
    }

    @Test fun requiresACallNotABareMention() {
        assertFalse(matches("# listed_person is the name-list verb"))
        assertFalse(matches("from x import name_list_records"))
    }

    @Test fun doesNotHighlightPersonInsideListedPerson() {
        // `person` precedes `listed_person` in the alternation, so a word boundary
        // is the only thing keeping it from matching the tail of the longer verb.
        val match = DslSyntaxAnnotator.DSL_FUNCTIONS.find("listed_person(1, ...)")
        assertEquals("listed_person", match?.value)
        assertEquals(0, match?.range?.first)
    }
}
