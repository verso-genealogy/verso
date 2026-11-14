package com.genealogy.dsllint

/**
 * Match DSL files: <village>_<type>_<year>[_<archive_suffix>...].py
 * Same regex as vscode-dsllint/src/fileDetection.ts.
 */
object DslFileDetector {
    private val PATTERN = Regex(
        "^[a-z_]+_(births|marriages|deaths|divorces|census|confessions|external_sources|name_lists)_\\d{4}(?:_[\\w-]+)*\\.py$"
    )

    fun isDslFile(fileName: String): Boolean {
        val base = fileName.substringAfterLast('/')
        return PATTERN.matches(base)
    }
}
