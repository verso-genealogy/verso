package com.genealogy.dsllint.settings

import com.intellij.openapi.options.Configurable
import com.intellij.ui.dsl.builder.bindSelected
import com.intellij.ui.dsl.builder.bindText
import com.intellij.ui.dsl.builder.panel
import javax.swing.JComponent
import com.intellij.openapi.ui.DialogPanel

class DslLintConfigurable : Configurable {

    private val settings get() = DslLintSettings.getInstance()
    private var panel: DialogPanel? = null

    override fun getDisplayName(): String = "DSL Lint"

    override fun createComponent(): JComponent {
        val state = settings.state
        val built = panel {
            row("Python interpreter:") {
                textField()
                    .bindText(state::pythonPath)
                    .comment("Used to invoke dsllint.py (default: python3)")
            }
            row {
                checkBox("Lint on open").bindSelected(state::lintOnOpen)
            }
            row {
                checkBox("Lint on save").bindSelected(state::lintOnSave)
            }
            row {
                checkBox("Log lint timing (diagnostics)")
                    .bindSelected(state::debugTiming)
                    .comment("Logs per-phase lint timing to idea.log (category com.genealogy.dsllint.timing)")
            }
        }
        panel = built
        return built
    }

    override fun isModified(): Boolean = panel?.isModified() ?: false

    override fun apply() {
        panel?.apply()
    }

    override fun reset() {
        panel?.reset()
    }

    override fun disposeUIResources() {
        panel = null
    }
}
