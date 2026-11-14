package com.genealogy.dsllint.settings

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage
import com.intellij.util.xmlb.XmlSerializerUtil

@State(name = "DslLintSettings", storages = [Storage("dsllint.xml")])
class DslLintSettings : PersistentStateComponent<DslLintSettings.State> {

    data class State(
        var pythonPath: String = "python3",
        var lintOnOpen: Boolean = true,
        var lintOnSave: Boolean = true,
        // Diagnostics: when on, the lint pipeline logs per-phase timing to idea.log
        // (category com.genealogy.dsllint.timing). Default off → zero overhead.
        var debugTiming: Boolean = false,
    )

    private var state = State()

    override fun getState(): State = state

    override fun loadState(state: State) {
        XmlSerializerUtil.copyBean(state, this.state)
    }

    var pythonPath: String
        get() = state.pythonPath
        set(value) { state.pythonPath = value }

    var lintOnOpen: Boolean
        get() = state.lintOnOpen
        set(value) { state.lintOnOpen = value }

    var lintOnSave: Boolean
        get() = state.lintOnSave
        set(value) { state.lintOnSave = value }

    var debugTiming: Boolean
        get() = state.debugTiming
        set(value) { state.debugTiming = value }

    companion object {
        fun getInstance(): DslLintSettings =
            ApplicationManager.getApplication().getService(DslLintSettings::class.java)
    }
}
