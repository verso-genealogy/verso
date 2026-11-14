package com.genealogy.dsllint.lint

/**
 * JSON output schema of `dsllint.py --json`.
 * Keep in sync with vscode-dsllint/src/diagnostics.ts.
 */
data class DslLintFix(
    val type: String, // "replace_kwarg" | "remove_kwarg" | "remove_arg"
    val old: String? = null,
    val new: String? = null,
    val kwarg: String? = null,
    // For replace_kwarg/remove_kwarg: 0-based char column where the target
    // `kwarg=value` token starts (pins the occurrence on lines with several
    // matching kwargs; null = legacy first-match). For remove_arg: the 0-based
    // char column where the positional argument begins.
    val col: Int? = null,
    // remove_arg only: 0-based char column just past the positional argument's
    // last char. JSON key is `end_col` (matched by Gson's default naming).
    val end_col: Int? = null,
)

data class DslLintIssue(
    val level: String, // "error" | "warn"
    val line: Int,
    val message: String,
    // What the finding is, in no language: its code, the message's params (what the DSL
    // wrote; a nested message is {key, params}) and the token it is about. Null in the output of
    // a dsllint from before them.
    val code: String? = null,
    val params: Map<String, Any?>? = null,
    val token: String? = null,
    // Optional issue-level highlight span (0-based char columns of the exact
    // flagged token, e.g. ULC001's string literal). Preferred over any
    // fix-derived or message-derived range: it pins THIS occurrence when the
    // same text appears earlier on the line.
    val col: Int? = null,
    val end_col: Int? = null,
    val fix: DslLintFix? = null,
)

data class DslLintResult(
    val file: String,
    val linter: String,
    val issues: List<DslLintIssue>,
)
