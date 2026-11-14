package com.genealogy.dsllint.actions

import com.genealogy.dsllint.DslFileDetector
import com.intellij.codeInsight.daemon.DaemonCodeAnalyzer
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.Task
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import com.intellij.psi.search.FilenameIndex
import com.intellij.psi.search.GlobalSearchScope

class LintAllAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        ProgressManager.getInstance().run(object : Task.Backgroundable(project, "Linting DSL files", true) {
            override fun run(indicator: ProgressIndicator) {
                // ReadAction.nonBlocking, not compute/run: those are deprecated from 2026.3,
                // and their replacements (computeBlocking/runBlocking) do not exist in 2025.3.
                val dslFiles = ReadAction.nonBlocking<List<VirtualFile>> {
                    FilenameIndex.getAllFilesByExt(project, "py", GlobalSearchScope.projectScope(project))
                        .filter { DslFileDetector.isDslFile(it.name) }
                }.executeSynchronously()
                val psiManager = PsiManager.getInstance(project)
                val daemon = DaemonCodeAnalyzer.getInstance(project)
                val total = dslFiles.size
                dslFiles.forEachIndexed { idx, vFile ->
                    indicator.checkCanceled()
                    indicator.fraction = idx.toDouble() / total.coerceAtLeast(1)
                    indicator.text2 = vFile.name
                    val psi = ReadAction.nonBlocking<PsiFile?> { psiManager.findFile(vFile) }
                        .executeSynchronously() ?: return@forEachIndexed
                    ApplicationManager.getApplication().invokeLater {
                        daemon.restart(psi, "DSL Lint: Lint All DSL Files")
                    }
                }
            }
        })
    }
}
