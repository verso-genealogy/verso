package com.genealogy.dsllint.lint

import com.intellij.openapi.Disposable
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.editor.EditorFactory
import com.intellij.openapi.editor.event.DocumentEvent
import com.intellij.openapi.editor.event.DocumentListener
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.ProjectActivity

/**
 * Records the wall-clock time of the last edit to each document (into
 * [DslLintTiming.LAST_EDIT_NANOS]) so the annotator can measure the edit → external
 * pass gap (G). Only records when timing telemetry is enabled, so the cost when
 * off is a single boolean read per keystroke. Disposed with the project.
 */
@Service(Service.Level.PROJECT)
class DslLintEditTracker : Disposable {
    init {
        EditorFactory.getInstance().eventMulticaster.addDocumentListener(
            object : DocumentListener {
                override fun documentChanged(event: DocumentEvent) {
                    if (!DslLintTiming.enabled()) return
                    event.document.putUserData(DslLintTiming.LAST_EDIT_NANOS, System.nanoTime())
                }
            },
            this,
        )
    }

    override fun dispose() {}
}

/** Bootstraps [DslLintEditTracker] at project startup so its listener is registered. */
class DslLintTimingStartup : ProjectActivity {
    override suspend fun execute(project: Project) {
        project.service<DslLintEditTracker>()
    }
}
