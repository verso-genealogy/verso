package com.genealogy.dsllint.quickfix

/**
 * Pure range-finding logic for quick fixes.
 * Ports vscode-dsllint/src/quickfixUtils.ts so the two implementations stay in sync.
 */
object KwargRangeFinder {

    /**
     * Find [start, end) range of `needle` on `lineText`, or null if absent.
     * When `fromCol` is given (0-based char column where the target kwarg starts),
     * search from there so the correct occurrence is found on lines with several
     * matching tokens. Null = legacy first-match behavior.
     */
    fun findReplaceRange(lineText: String, needle: String, fromCol: Int? = null): IntRange? {
        val start = fromCol?.coerceIn(0, lineText.length) ?: 0
        val idx = lineText.indexOf(needle, start)
        if (idx == -1) return null
        return idx until (idx + needle.length)
    }

    /**
     * Find the range of `kwarg=value` on the line, with no surrounding separator.
     * Suitable for highlighting just the offending argument. When `fromCol` is
     * given (0-based char column where the kwarg starts), match from there so the
     * correct occurrence is found on lines with several `kwarg=` tokens.
     */
    fun findKwargRange(lineText: String, kwarg: String, fromCol: Int? = null): IntRange? {
        val pattern = Regex("${Regex.escape(kwarg)}=(?:\"[^\"]*\"|[A-Za-z_][A-Za-z0-9_]*)")
        val start = fromCol?.coerceIn(0, lineText.length) ?: 0
        val match = pattern.find(lineText, start) ?: return null
        return match.range.first until (match.range.last + 1)
    }

    /**
     * The issue's own token (what the finding is about, in no language) on the line — its
     * first occurrence as a whole word (Иван, not the start of Ивановъ), else its first occurrence
     * — or null when it is not there. A message reworded, or read in another language, still finds
     * it; `findMessageTokenRange` stays for older dsllint output.
     */
    fun findTokenRange(lineText: String, token: String?): IntRange? {
        if (token.isNullOrEmpty()) return null
        val first = lineText.indexOf(token)
        var idx = first
        while (idx != -1) {
            val end = idx + token.length
            val before = lineText.getOrNull(idx - 1)
            val after = lineText.getOrNull(end)
            if ((before == null || !before.isLetterOrDigit() && before != '_') &&
                (after == null || !after.isLetterOrDigit() && after != '_')) {
                return idx until end
            }
            idx = lineText.indexOf(token, idx + 1)
        }
        return if (first == -1) null else first until (first + token.length)
    }

    /**
     * For issues without fix metadata (e.g. the `names` linter), locate the
     * offending source token quoted in the message so the highlight can be
     * narrowed from the whole line to just that token.
     *
     * Messages quote the value as it appears in source, optionally with a
     * normalized form: `Unknown first name 'Ерас' (from 'Ерасъ')`. The
     * `(from '...')` literal is the exact source text, so it is preferred;
     * otherwise the first single-quoted token is used.
     *
     * Some linters (e.g. `relationship_ref`) quote the offending value with
     * double quotes and carry no fix metadata: `relationship_ref="восприемник
     * №2" is not allowed; use one of: ...`. There the first double-quoted token
     * is the offending value, so it is used (kept with its quotes, mirroring
     * the `replace_kwarg` highlight).
     *
     * Some linters (e.g. `patronymic_form` PAF001) quote the offending source
     * token with guillemets: `full patronymic «Ивановичъ» on a non-high-rank
     * person …`. The first «…» token is the offending value; its inner text (no
     * guillemets) is used as a final fallback, since the source renders it
     * inside ordinary quotes.
     *
     * When a message quotes several tokens — e.g. an "expected" value contrasted
     * with the actual one (`should contain 'familio.org/catalogs/vss' or
     * 'viewer.rsl.ru' …; got 'https://…'`) — only the token that actually appears
     * on the line is the offending source; the expected values are not on the
     * line and must never be the narrow target. So gather the candidates in
     * preference order and return the first one present on `lineText`.
     *
     * Returns the [start, end) range on `lineText`, or null if no quoted token
     * from the message is found on the line.
     */
    fun findMessageTokenRange(lineText: String, message: String): IntRange? {
        val candidates = mutableListOf<String>()
        // Preferred: the exact source text in a `(from '...')` clause.
        Regex("\\(from '([^']*)'\\)").find(message)?.groupValues?.get(1)
            ?.takeIf { it.isNotEmpty() }?.let { candidates.add(it) }
        // Single-quoted tokens (inner text), in order.
        Regex("'([^']+)'").findAll(message).forEach { candidates.add(it.groupValues[1]) }
        // Double-quoted tokens (kept WITH quotes, mirroring the replace_kwarg highlight).
        Regex("\"[^\"]+\"").findAll(message).forEach { candidates.add(it.value) }
        // Guillemet tokens (inner text — the source renders them in ordinary quotes).
        Regex("«([^»]+)»").findAll(message).forEach { candidates.add(it.groupValues[1]) }
        for (token in candidates) {
            val idx = lineText.indexOf(token)
            if (idx != -1) return idx until (idx + token.length)
        }
        return null
    }

    /**
     * Find the range to remove for `kwarg=value`, optionally consuming the
     * surrounding `", "` separator. Prefers leading `", "` (kwarg is mid-list);
     * falls back to trailing `", "` (kwarg is first of the kwargs).
     */
    fun findRemoveRange(lineText: String, kwarg: String, fromCol: Int? = null): IntRange? {
        val core = findKwargRange(lineText, kwarg, fromCol) ?: return null
        var start = core.first
        var end = core.last + 1

        if (start >= 2 && lineText.substring(start - 2, start) == ", ") {
            start -= 2
        } else if (end + 2 <= lineText.length && lineText.substring(end, end + 2) == ", ") {
            end += 2
        }

        return start until end
    }

    /**
     * Find the range to remove for a positional argument given its [startCol, endCol)
     * char columns (from the linter's `col`/`end_col`). Extends to consume the
     * separating `", "` so the call stays well-formed: prefers the leading `", "`
     * (arg is not first), else a trailing `", "`.
     */
    fun findRemoveArgRange(lineText: String, startCol: Int, endCol: Int): IntRange {
        var start = startCol.coerceIn(0, lineText.length)
        var end = endCol.coerceIn(start, lineText.length)

        if (start >= 2 && lineText.substring(start - 2, start) == ", ") {
            start -= 2
        } else if (end + 2 <= lineText.length && lineText.substring(end, end + 2) == ", ") {
            end += 2
        }

        return start until end
    }
}
