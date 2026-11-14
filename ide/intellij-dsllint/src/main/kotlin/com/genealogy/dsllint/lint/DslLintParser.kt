package com.genealogy.dsllint.lint

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

object DslLintParser {
    private val gson = Gson()
    private val resultListType = object : TypeToken<List<DslLintResult>>() {}.type

    /** Parse `dsllint.py --json` stdout. Returns empty list on blank/invalid input. */
    fun parse(json: String): List<DslLintResult> {
        val trimmed = json.trim()
        if (trimmed.isEmpty()) return emptyList()
        return try {
            gson.fromJson<List<DslLintResult>>(trimmed, resultListType) ?: emptyList()
        } catch (_: Exception) {
            emptyList()
        }
    }
}
