package com.genealogy.dsllint.lint

import com.genealogy.dsllint.DslFileDetector
import com.genealogy.dsllint.quickfix.KwargRangeFinder
import com.genealogy.dsllint.quickfix.RemoveArgFix
import com.genealogy.dsllint.quickfix.RemoveKwargFix
import com.genealogy.dsllint.quickfix.ReplaceKwargFix
import com.genealogy.dsllint.settings.DslLintSettings
import com.intellij.lang.annotation.AnnotationHolder
import com.intellij.lang.annotation.ExternalAnnotator
import com.intellij.lang.annotation.HighlightSeverity
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.progress.ProcessCanceledException
import com.intellij.openapi.util.TextRange
import com.intellij.psi.PsiFile
import java.io.File

/**
 * IntelliJ equivalent of the VS Code extension's lint-on-edit pipeline.
 *
 * - `collectInformation` runs on the EDT; cheap filtering and capture only.
 * - `doAnnotate` runs off-EDT; shells out to `dsllint.py --json`.
 * - `apply` runs on the EDT; converts results into annotations + intentions.
 */
class DslLintAnnotator :
    ExternalAnnotator<DslLintAnnotator.CollectedInfo, List<DslLintResult>>() {

    data class CollectedInfo(
        val filePath: String,
        val pythonPath: String,
        val linterScript: File,
        // The live document text captured on the EDT, linted via a temp file so results
        // reflect unsaved edits (otherwise findings lag until the IDE auto-saves to disk).
        val documentText: String?,
        // Telemetry (only populated when DslLintTiming.enabled()): a per-pass id
        // and the wall-clock at which this external pass began collecting.
        val passId: Long = -1,
        val collectNanos: Long = 0,
    )

    override fun collectInformation(file: PsiFile, editor: Editor, hasErrors: Boolean): CollectedInfo? {
        return collectInformation(file)
    }

    override fun collectInformation(file: PsiFile): CollectedInfo? {
        val vFile = file.virtualFile ?: return null
        if (!DslFileDetector.isDslFile(vFile.name)) return null
        val filePath = vFile.path
        val script = DslLintRunner.findLinterScript(file.project) ?: return null
        val pythonPath = DslLintSettings.getInstance().pythonPath
        // Snapshot the live document text here (EDT/read-action) so doAnnotate lints the
        // in-memory edits, not the stale on-disk file.
        val documentText = file.viewProvider.document?.text

        if (!DslLintTiming.enabled()) {
            return CollectedInfo(filePath, pythonPath, script, documentText)
        }
        // G = edit → external pass start. The headline metric: this is the
        // platform's deferral, the time the daemon waited before scheduling us.
        val now = System.nanoTime()
        val passId = DslLintTiming.nextPassId()
        DslLintTiming.collectCount.incrementAndGet()
        // Do NOT consume the edit timestamp here — it is consumed at apply() so we can
        // measure end-to-end L (edit→apply, when the red actually clears). Not consuming
        // also makes the retry chain visible: each canceled-then-retried pass logs a
        // growing G against the same edit until one completes.
        val editNanos = file.viewProvider.document?.getUserData(DslLintTiming.LAST_EDIT_NANOS)
        val gap = if (editNanos != null) "${DslLintTiming.ms(editNanos, now)}ms" else "n/a (not edit-triggered)"
        DslLintTiming.log("pass=$passId collectInformation: G(edit->collect)=$gap file=${vFile.name}")
        return CollectedInfo(filePath, pythonPath, script, documentText, passId, now)
    }

    override fun doAnnotate(collectedInfo: CollectedInfo?): List<DslLintResult> {
        if (collectedInfo == null) return emptyList()
        if (!DslLintTiming.enabled()) {
            return DslLintRunner.run(
                pythonPath = collectedInfo.pythonPath,
                linterScript = collectedInfo.linterScript,
                filePath = collectedInfo.filePath,
                content = collectedInfo.documentText,
            )
        }
        val start = System.nanoTime()
        DslLintTiming.doAnnotateStartCount.incrementAndGet()
        try {
            val result = DslLintRunner.run(
                pythonPath = collectedInfo.pythonPath,
                linterScript = collectedInfo.linterScript,
                filePath = collectedInfo.filePath,
                content = collectedInfo.documentText,
            )
            val end = System.nanoTime()
            DslLintTiming.doAnnotateDoneCount.incrementAndGet()
            // D = doAnnotate (incl. dsllint.py subprocess; see DslLintRunner for the
            // subprocess/parse split). starts/dones counters expose restart churn.
            DslLintTiming.log(
                "pass=${collectedInfo.passId} doAnnotate: D=${DslLintTiming.ms(start, end)}ms" +
                    " starts=${DslLintTiming.doAnnotateStartCount.get()} dones=${DslLintTiming.doAnnotateDoneCount.get()}"
            )
            return result
        } catch (e: ProcessCanceledException) {
            DslLintTiming.cancelCount.incrementAndGet()
            DslLintTiming.log(
                "pass=${collectedInfo.passId} doAnnotate CANCELED after ${DslLintTiming.ms(start, System.nanoTime())}ms" +
                    " cancels=${DslLintTiming.cancelCount.get()}"
            )
            throw e
        }
    }

    override fun apply(file: PsiFile, annotationResult: List<DslLintResult>, holder: AnnotationHolder) {
        val doc = file.viewProvider.document ?: return
        val applyStart = if (DslLintTiming.enabled()) System.nanoTime() else 0L
        for (result in annotationResult) {
            for (issue in result.issues) {
                val zeroLine = (issue.line - 1).coerceIn(0, (doc.lineCount - 1).coerceAtLeast(0))
                val lineStart = doc.getLineStartOffset(zeroLine)
                val lineEnd = doc.getLineEndOffset(zeroLine)
                val lineText = doc.getText(TextRange(lineStart, lineEnd))

                val narrowed = narrowRange(lineText, issue)
                val range = if (narrowed != null) {
                    TextRange(lineStart + narrowed.first, lineStart + narrowed.last + 1)
                } else {
                    TextRange(lineStart, lineEnd)
                }

                val severity = if (issue.level == "error") HighlightSeverity.ERROR else HighlightSeverity.WARNING
                val message = "[${result.linter}] ${issue.message}"

                var builder = holder.newAnnotation(severity, message).range(range)
                val fix = issue.fix
                if (fix != null) {
                    when (fix.type) {
                        "replace_kwarg" -> {
                            val old = fix.old
                            val new = fix.new
                            if (old != null && new != null) {
                                builder = builder.withFix(ReplaceKwargFix(issue.line, old, new, fix.col))
                            }
                        }
                        "remove_kwarg" -> {
                            val kwarg = fix.kwarg
                            if (kwarg != null) {
                                builder = builder.withFix(RemoveKwargFix(issue.line, kwarg, fix.col))
                            }
                        }
                        "remove_arg" -> {
                            val col = fix.col
                            val endCol = fix.end_col
                            if (col != null && endCol != null) {
                                builder = builder.withFix(
                                    RemoveArgFix(issue.line, fix.kwarg ?: "argument", col, endCol),
                                )
                            }
                        }
                    }
                }
                builder.create()
            }
        }
        if (DslLintTiming.enabled()) {
            val end = System.nanoTime()
            val issues = annotationResult.sumOf { it.issues.size }
            // L = edit → apply: the end-to-end latency the user feels (red clears at apply).
            // Consume the edit timestamp here so each edit yields one L (the clearing pass).
            val doc2 = file.viewProvider.document
            val editNanos = doc2?.getUserData(DslLintTiming.LAST_EDIT_NANOS)
            doc2?.putUserData(DslLintTiming.LAST_EDIT_NANOS, null)
            val l = if (editNanos != null) "${DslLintTiming.ms(editNanos, end)}ms" else "n/a"
            // A = apply (EDT annotation build) — expected tiny; L is the headline.
            DslLintTiming.log("apply: A=${DslLintTiming.ms(applyStart, end)}ms L(edit->apply)=$l issues=$issues")
        }
    }

    /**
     * If the issue carries enough metadata to locate the offending token,
     * return the in-line range to highlight; otherwise null (caller falls back
     * to the full line). Multi-line / structural issues stay full-line.
     *
     * Issue-level col/end_col (the linter pinning the exact flagged token,
     * e.g. ULC001's string literal) is the most precise source — it survives
     * lines where the same text appears more than once. Next comes fix
     * metadata (kwarg fixes), then the issue's token. Lacking all three (older
     * dsllint output), fall back to the source token quoted in the message —
     * this narrows `names` linter issues (e.g.
     * "Unknown first name") to just the offending name, but always hits the
     * FIRST occurrence.
     */
    private fun narrowRange(lineText: String, issue: DslLintIssue): IntRange? {
        val issueCol = issue.col
        val issueEndCol = issue.end_col
        if (issueCol != null && issueEndCol != null && issueCol < issueEndCol) {
            return issueCol.coerceIn(0, lineText.length) until
                issueEndCol.coerceIn(issueCol, lineText.length)
        }
        val fix = issue.fix
        val message = issue.message
        if (fix != null) {
            return when (fix.type) {
                "replace_kwarg" -> fix.old?.let { KwargRangeFinder.findReplaceRange(lineText, it, fix.col) }
                "remove_kwarg" -> fix.kwarg?.let { KwargRangeFinder.findKwargRange(lineText, it, fix.col) }
                "remove_arg" -> {
                    val col = fix.col
                    val endCol = fix.end_col
                    // Highlight just the positional argument (without the separator).
                    if (col != null && endCol != null && col <= endCol) {
                        col.coerceIn(0, lineText.length) until endCol.coerceIn(col, lineText.length)
                    } else {
                        null
                    }
                }
                else -> null
            }
        }
        return KwargRangeFinder.findTokenRange(lineText, issue.token)
            ?: KwargRangeFinder.findMessageTokenRange(lineText, message)
    }
}
