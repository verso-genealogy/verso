package com.genealogy.dsllint.lint

import com.genealogy.dsllint.DslFileDetector
import com.intellij.codeInsight.daemon.DaemonCodeAnalyzer
import com.intellij.openapi.Disposable
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.EditorFactory
import com.intellij.openapi.editor.event.DocumentEvent
import com.intellij.openapi.editor.event.DocumentListener
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.roots.ProjectFileIndex
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.psi.PsiManager
import com.intellij.util.Alarm

/**
 * Re-lints open DSL files when a linter *dependency* file (e.g. `verso/ru/dsl/statuses.py`)
 * is edited.
 *
 * The [DslLintAnnotator] is an `ExternalAnnotator`, so the platform only re-runs it for a
 * file when *that* file's document changes. `statuses.py` is a dependency of every DSL file
 * — adding a `Status` constant changes what `dsllint.py` reports — but editing it does not
 * invalidate the cached annotations on the record files. The result was the surprise where
 * a newly-added constant only started being flagged after an unrelated IDE restart forced a
 * fresh lint. This watcher closes that gap by nudging the daemon to re-analyze the open DSL
 * files whenever a dependency changes.
 *
 * Two listeners feed the same debounced re-lint:
 * - a [DocumentListener] for in-editor edits (dependency file open in a tab), and
 * - a VFS [BulkFileListener] for on-disk changes with no open document — e.g. a
 *   `git checkout` / branch switch / external edit that swaps `statuses.py` on disk.
 *
 * Edits are debounced (dependency files are edited keystroke-by-keystroke like any other),
 * and only *open* DSL files are restarted — closed files lint fresh when next opened.
 * Disposed with the project.
 */
@Service(Service.Level.PROJECT)
class DslLintDependencyWatcher(private val project: Project) : Disposable {
    private val alarm = Alarm(Alarm.ThreadToUse.SWING_THREAD, this)

    init {
        EditorFactory.getInstance().eventMulticaster.addDocumentListener(
            object : DocumentListener {
                override fun documentChanged(event: DocumentEvent) {
                    val vFile = FileDocumentManager.getInstance().getFile(event.document) ?: return
                    if (isRelevantDependency(vFile)) scheduleRelint()
                }
            },
            this,
        )
        project.messageBus.connect(this).subscribe(
            VirtualFileManager.VFS_CHANGES,
            object : BulkFileListener {
                override fun after(events: List<VFileEvent>) {
                    if (events.any { event -> event.file?.let { isRelevantDependency(it) } == true }) {
                        scheduleRelint()
                    }
                }
            },
        )
    }

    /**
     * A dependency file that belongs to this project. The document multicaster and the VFS
     * bus are both application-wide, so filter to this project's content to avoid re-linting
     * on an unrelated project's `statuses.py`.
     */
    private fun isRelevantDependency(vFile: VirtualFile): Boolean =
        DslLintDependencies.isDependencyFile(vFile.name) &&
            ProjectFileIndex.getInstance(project).isInContent(vFile)

    private fun scheduleRelint() {
        if (project.isDisposed) return
        alarm.cancelAllRequests()
        alarm.addRequest({ relintOpenDslFiles() }, RELINT_DEBOUNCE_MS)
    }

    /** Runs on the SWING (EDT) thread via the alarm; safe to touch editors and the daemon. */
    private fun relintOpenDslFiles() {
        if (project.isDisposed) return
        val psiManager = PsiManager.getInstance(project)
        val daemon = DaemonCodeAnalyzer.getInstance(project)
        FileEditorManager.getInstance(project).openFiles
            .filter { DslFileDetector.isDslFile(it.name) }
            .forEach { vFile ->
                val psi = psiManager.findFile(vFile) ?: return@forEach
                daemon.restart(psi, "DSL Lint: linter dependency changed")
            }
    }

    override fun dispose() {}

    companion object {
        private const val RELINT_DEBOUNCE_MS = 400
    }
}

/** Bootstraps [DslLintDependencyWatcher] at project startup so its listener is registered. */
class DslLintDependencyWatcherStartup : ProjectActivity {
    override suspend fun execute(project: Project) {
        project.service<DslLintDependencyWatcher>()
    }
}
