package com.genealogy.dsllint.lint

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.CapturingProcessHandler
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import java.io.File
import java.nio.charset.StandardCharsets

object DslLintRunner {
    private val LOG = Logger.getInstance(DslLintRunner::class.java)
    private const val TIMEOUT_MS = 30_000

    /**
     * Walk up from `start` looking for `dsllint.py`. Returns its absolute path or null.
     * Mirrors `findLinterScript` in vscode-dsllint, but supports nested projects.
     */
    fun findLinterScript(start: String?): File? {
        if (start.isNullOrEmpty()) return null
        var dir: File? = File(start)
        while (dir != null) {
            val candidate = File(dir, "dsllint.py")
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        return null
    }

    fun findLinterScript(project: Project): File? = findLinterScript(project.basePath)

    /**
     * Invoke `<python> dsllint.py --json <file>` and return parsed results.
     * Returns an empty list on any failure (timeout, non-zero exit with empty stdout, JSON parse error).
     *
     * When [content] is supplied (the live, possibly-unsaved document text), it is linted via
     * a temp file so results reflect in-memory edits — otherwise findings would lag until the
     * IDE auto-saves to disk. All dsllint linters depend only on file content (they report
     * line numbers; village/landlord context comes from the records, not the path), so a temp
     * file in the system temp dir is equivalent and line numbers map 1:1 to the editor.
     * With no [content], the on-disk [filePath] is linted (unchanged legacy behavior).
     */
    fun run(
        pythonPath: String,
        linterScript: File,
        filePath: String,
        content: String? = null,
    ): List<DslLintResult> {
        var tempFile: File? = null
        val target = if (content != null) {
            tempFile = File.createTempFile("dsllint-", ".py").apply { writeText(content, Charsets.UTF_8) }
            tempFile.absolutePath
        } else {
            filePath
        }
        try {
            return runOn(pythonPath, linterScript, target, filePath)
        } finally {
            tempFile?.delete()
        }
    }

    private fun runOn(
        pythonPath: String,
        linterScript: File,
        target: String,
        filePath: String,
    ): List<DslLintResult> {
        val cmd = GeneralCommandLine(pythonPath, linterScript.absolutePath, "--json", target)
            .withWorkDirectory(linterScript.parentFile)
            .withCharset(StandardCharsets.UTF_8)

        val subStart = System.nanoTime()
        val output = try {
            CapturingProcessHandler(cmd).runProcess(TIMEOUT_MS)
        } catch (e: Exception) {
            LOG.warn("dsllint: failed to spawn linter: ${e.message}")
            return emptyList()
        }
        val subEnd = System.nanoTime()

        if (output.isTimeout) {
            LOG.warn("dsllint: timed out after ${TIMEOUT_MS}ms on $filePath")
            return emptyList()
        }

        val stdout = output.stdout
        if (stdout.isBlank()) {
            val stderr = output.stderr
            if (stderr.isNotBlank()) LOG.debug("dsllint stderr: $stderr")
            DslLintTiming.log("subprocess=${DslLintTiming.ms(subStart, subEnd)}ms (blank stdout)")
            return emptyList()
        }

        val parsed = DslLintParser.parse(stdout)
        // Splits D into the subprocess vs JSON-parse halves — both expected small,
        // so they cannot account for the perceived "reflect fixes" lag.
        DslLintTiming.log(
            "subprocess=${DslLintTiming.ms(subStart, subEnd)}ms" +
                " parse=${DslLintTiming.ms(subEnd, System.nanoTime())}ms"
        )
        return parsed
    }
}
