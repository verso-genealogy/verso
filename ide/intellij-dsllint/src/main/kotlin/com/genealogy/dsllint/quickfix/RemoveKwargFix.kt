package com.genealogy.dsllint.quickfix

import com.intellij.codeInsight.intention.IntentionAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiFile

/**
 * Quick fix that removes a `kwarg=value` (with surrounding `", "` separator) on `line` (1-based).
 * Maps to fix.type == "remove_kwarg" from dsllint.py JSON output.
 */
class RemoveKwargFix(
    private val line: Int,
    private val kwarg: String,
    private val col: Int? = null,
) : IntentionAction {

    override fun getText(): String = "Remove redundant $kwarg"

    override fun getFamilyName(): String = "DSL Lint"

    override fun isAvailable(project: Project, editor: Editor?, file: PsiFile?): Boolean {
        val lineText = lineTextOrNull(file) ?: return false
        return KwargRangeFinder.findRemoveRange(lineText, kwarg, col) != null
    }

    override fun invoke(project: Project, editor: Editor?, file: PsiFile?) {
        if (file == null) return
        val doc = file.viewProvider.document ?: return
        val zeroLine = line - 1
        if (zeroLine < 0 || zeroLine >= doc.lineCount) return
        val start = doc.getLineStartOffset(zeroLine)
        val end = doc.getLineEndOffset(zeroLine)
        val lineText = doc.getText(TextRange(start, end))
        val range = KwargRangeFinder.findRemoveRange(lineText, kwarg, col) ?: return
        doc.deleteString(start + range.first, start + range.last + 1)
    }

    override fun startInWriteAction(): Boolean = true

    private fun lineTextOrNull(file: PsiFile?): String? {
        if (file == null) return null
        val doc = file.viewProvider.document ?: return null
        val zeroLine = line - 1
        if (zeroLine < 0 || zeroLine >= doc.lineCount) return null
        return doc.getText(
            TextRange(doc.getLineStartOffset(zeroLine), doc.getLineEndOffset(zeroLine))
        )
    }
}
