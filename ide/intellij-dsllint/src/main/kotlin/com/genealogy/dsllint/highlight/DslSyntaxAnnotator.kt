package com.genealogy.dsllint.highlight

import com.genealogy.dsllint.DslFileDetector
import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.Annotator
import com.intellij.lang.annotation.HighlightSeverity
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile

/**
 * Ports the TextMate injection grammar from
 * vscode-dsllint/syntaxes/genealogy-dsl.injection.tmLanguage.json.
 *
 * The Annotator framework visits every PSI element during a highlight pass.
 * We only do real work when we see the PsiFile root — and only for DSL files —
 * then sweep the entire document text once with the same regexes.
 */
class DslSyntaxAnnotator : Annotator {

    override fun annotate(element: PsiElement, holder: AnnotationHolder) {
        if (element !is PsiFile) return
        val vFile = element.virtualFile ?: return
        if (!DslFileDetector.isDslFile(vFile.name)) return

        val baseOffset = element.textRange.startOffset
        val text = element.text

        annotateMatches(text, baseOffset, holder, DSL_FUNCTIONS, DslTextAttributes.DSL_FUNCTION)
        annotateMatches(text, baseOffset, holder, GENDER_ENUM, DslTextAttributes.DSL_GENDER_ENUM)
        annotateMatches(text, baseOffset, holder, MONTH_ENUM, DslTextAttributes.DSL_MONTH_ENUM)
        annotateMatches(text, baseOffset, holder, STATUS_CONST, DslTextAttributes.DSL_STATUS_CONST)
    }

    private fun annotateMatches(
        text: String,
        baseOffset: Int,
        holder: AnnotationHolder,
        regex: Regex,
        attr: com.intellij.openapi.editor.colors.TextAttributesKey,
    ) {
        for (match in regex.findAll(text)) {
            val range = TextRange(baseOffset + match.range.first, baseOffset + match.range.last + 1)
            holder.newSilentAnnotation(HighlightSeverity.INFORMATION)
                .range(range)
                .textAttributes(attr)
                .create()
        }
    }

    companion object {
        // `internal`, not `private`: these regexes are a hand-kept port of
        // vscode-dsllint's TextMate grammar, and nothing but a test can catch the
        // two drifting apart. See DslSyntaxAnnotatorTest.
        internal val DSL_FUNCTIONS = Regex(
            "\\b(?:person|birth|death|marriage|page|book|relative|" +
                "birth_month|death_month|marriage_month|" +
                "birth_records|death_records|marriage_records|" +
                "birth_month_year|death_month_year|marriage_month_year|" +
                "name_list_records|listed_person|" +
                "RecordDefaults)(?=\\s*\\()"
        )
        private val GENDER_ENUM = Regex("\\bGender\\.(?:MALE|FEMALE)\\b")
        private val MONTH_ENUM = Regex(
            "\\bMonth\\.(?:JANUARY|FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER)\\b"
        )
        private val STATUS_CONST = Regex("\\b[A-Z][A-Z_]{2,}\\b")
    }
}
