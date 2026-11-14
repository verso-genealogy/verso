package com.genealogy.dsllint.actions

import com.genealogy.dsllint.DslFileDetector
import com.intellij.codeInsight.daemon.DaemonCodeAnalyzer
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys

class LintCurrentFileAction : AnAction() {
    // update() reads CommonDataKeys.PSI_FILE, a slow data key that must be
    // resolved off the EDT. Run action update on the background thread.
    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val psiFile = e.getData(CommonDataKeys.PSI_FILE) ?: return
        val vFile = psiFile.virtualFile ?: return
        if (!DslFileDetector.isDslFile(vFile.name)) return
        DaemonCodeAnalyzer.getInstance(project).restart(psiFile, "DSL Lint: Lint Current DSL File")
    }

    override fun update(e: AnActionEvent) {
        val psiFile = e.getData(CommonDataKeys.PSI_FILE)
        val vFile = psiFile?.virtualFile
        e.presentation.isEnabledAndVisible =
            vFile != null && DslFileDetector.isDslFile(vFile.name)
    }
}
