/**
 * Find the character range of a substring on a line.
 * When `fromCol` is given (0-based char column where the target kwarg starts),
 * search from there so the correct occurrence is found on lines with several
 * matching tokens. Returns [start, end] or null.
 */
export function findReplaceRange(
  lineText: string,
  needle: string,
  fromCol?: number
): [number, number] | null {
  const start = fromCol != null ? Math.max(0, Math.min(fromCol, lineText.length)) : 0;
  const idx = lineText.indexOf(needle, start);
  if (idx === -1) return null;
  return [idx, idx + needle.length];
}

/**
 * Find the range of `kwarg=value` on the line, with no surrounding separator.
 * Suitable for highlighting just the offending argument. When `fromCol` is given
 * (0-based char column where the kwarg starts), match from there so the correct
 * occurrence is found on lines with several `kwarg=` tokens.
 * Returns [start, end] or null.
 */
export function findKwargRange(
  lineText: string,
  kwarg: string,
  fromCol?: number
): [number, number] | null {
  // Match kwarg=VALUE where VALUE is either a quoted string or an identifier
  const pattern = new RegExp(
    `${kwarg}=(?:"[^"]*"|[A-Za-z_][A-Za-z0-9_]*)`
  );
  const start = fromCol != null ? Math.max(0, Math.min(fromCol, lineText.length)) : 0;
  const match = pattern.exec(lineText.slice(start));
  if (!match) return null;
  return [start + match.index, start + match.index + match[0].length];
}

/**
 * Find the range to remove for a kwarg (including comma separator).
 * Handles: `, kwarg=value` or `kwarg=value, ` patterns. `fromCol` pins the exact
 * occurrence (see findKwargRange). Returns [start, end] or null.
 */
export function findRemoveRange(
  lineText: string,
  kwarg: string,
  fromCol?: number
): [number, number] | null {
  const core = findKwargRange(lineText, kwarg, fromCol);
  if (!core) return null;

  let [start, end] = core;

  // Try to consume leading ", " (preferred — kwarg is not the first arg)
  if (start >= 2 && lineText.substring(start - 2, start) === ", ") {
    start -= 2;
  }
  // Otherwise try to consume trailing ", " (kwarg is the first of kwargs)
  else if (lineText.substring(end, end + 2) === ", ") {
    end += 2;
  }

  return [start, end];
}

/**
 * Find the range to remove for a positional argument given its [start, end) char
 * columns (from the linter's `col`/`end_col`). Extends to consume the separating
 * `, ` so the call stays well-formed: prefers the leading `, ` (arg is not first),
 * else a trailing `, `. Returns [start, end].
 */
export function findRemoveArgRange(
  lineText: string,
  startCol: number,
  endCol: number
): [number, number] {
  let start = Math.max(0, Math.min(startCol, lineText.length));
  let end = Math.max(start, Math.min(endCol, lineText.length));
  if (start >= 2 && lineText.substring(start - 2, start) === ", ") {
    start -= 2;
  } else if (lineText.substring(end, end + 2) === ", ") {
    end += 2;
  }
  return [start, end];
}

/**
 * For issues without fix metadata, locate the offending source token quoted in
 * the message so the highlight can be narrowed from the whole line to just that
 * token.
 *
 * Messages quote the value as it appears in source, optionally with a
 * normalized form: `Unknown first name 'Ерас' (from 'Ерасъ')`. The `(from
 * '...')` literal is the exact source text, so it is preferred; otherwise the
 * first single-quoted token is used.
 *
 * Some linters (e.g. `relationship_ref`) quote the offending value with double
 * quotes and carry no fix metadata: `relationship_ref="восприемник №2" is not
 * allowed; use one of: ...`. There the first double-quoted token is the
 * offending value, so it is used (kept with its quotes, mirroring the
 * `replace_kwarg` highlight).
 *
 * Some linters (e.g. `patronymic_form` PAF001) quote the offending source token
 * with guillemets: `full patronymic «Ивановичъ» on a non-high-rank person …`.
 * The first «…» token is the offending value; its inner text (no guillemets) is
 * used as a final fallback, since the source renders it inside ordinary quotes.
 *
 * When a message quotes several tokens — e.g. an "expected" value contrasted
 * with the actual one (`should contain 'familio.org/catalogs/vss' or
 * 'viewer.rsl.ru' …; got 'https://…'`) — only the token that actually appears on
 * the line is the offending source; the others (the expected hosts) are not on
 * the line and must never be the narrow target. So gather the candidates in
 * preference order and return the first one present on `lineText`.
 *
 * Returns [start, end] on `lineText`, or null if no quoted token from the
 * message is found on the line.
 */
export function findMessageTokenRange(
  lineText: string,
  message: string
): [number, number] | null {
  const candidates: string[] = [];
  // Preferred: the exact source text in a `(from '...')` clause.
  const fromMatch = /\(from '([^']*)'\)/.exec(message);
  if (fromMatch && fromMatch[1].length > 0) candidates.push(fromMatch[1]);
  // Single-quoted tokens (inner text), in order.
  for (const m of message.matchAll(/'([^']+)'/g)) candidates.push(m[1]);
  // Double-quoted tokens (kept WITH quotes, mirroring the replace_kwarg highlight).
  for (const m of message.matchAll(/"[^"]+"/g)) candidates.push(m[0]);
  // Guillemet tokens (inner text — the source renders them in ordinary quotes).
  for (const m of message.matchAll(/«([^»]+)»/g)) candidates.push(m[1]);
  for (const token of candidates) {
    const idx = lineText.indexOf(token);
    if (idx !== -1) return [idx, idx + token.length];
  }
  return null;
}

const LETTER = /[\p{L}\p{N}_]/u;

/**
 * The issue's own token (what the finding is about, in no language) on the line: its first
 * occurrence as a whole word (Иван, not the start of Ивановъ), else its first occurrence, or null
 * when it is not there — a message reworded or read in another language still finds it.
 */
export function findTokenRange(lineText: string, token: string | null | undefined): [number, number] | null {
  if (!token) return null;
  const first = lineText.indexOf(token);
  for (let idx = first; idx !== -1; idx = lineText.indexOf(token, idx + 1)) {
    const end = idx + token.length;
    if (!LETTER.test(lineText.charAt(idx - 1)) && !LETTER.test(lineText.charAt(end))) return [idx, end];
  }
  return first === -1 ? null : [first, first + token.length];
}

export interface NarrowFix {
  type: "replace_kwarg" | "remove_kwarg" | "remove_arg";
  old?: string;
  new?: string;
  kwarg?: string;
  // 0-based char column where the target `kwarg=value` token starts. Pins the
  // exact occurrence when a line carries several matching kwargs. For remove_arg,
  // the column where the positional argument begins.
  col?: number;
  // remove_arg only: char column just past the positional argument's last char.
  end_col?: number;
}

/**
 * If the issue carries enough metadata to locate the offending token, return
 * the in-line range to highlight; otherwise null (caller falls back to the full
 * line). Multi-line / structural issues stay full-line.
 *
 * Fix metadata (kwarg fixes) is the most precise source. Lacking that, the
 * issue's token; lacking that (older dsllint output), the source token quoted
 * in the message.
 */
export function narrowRange(
  lineText: string,
  fix: NarrowFix | undefined,
  message: string,
  token?: string | null
): [number, number] | null {
  if (fix) {
    if (fix.type === "replace_kwarg" && fix.old) {
      return findReplaceRange(lineText, fix.old, fix.col);
    }
    if (fix.type === "remove_kwarg" && fix.kwarg) {
      return findKwargRange(lineText, fix.kwarg, fix.col);
    }
    if (fix.type === "remove_arg" && fix.col != null && fix.end_col != null) {
      // Highlight just the positional argument (without the separator).
      return [
        Math.max(0, Math.min(fix.col, lineText.length)),
        Math.max(0, Math.min(fix.end_col, lineText.length)),
      ];
    }
    return null;
  }
  return findTokenRange(lineText, token) ?? findMessageTokenRange(lineText, message);
}

/**
 * narrowRange for a whole issue: prefer the issue-level col/end_col span (the
 * linter pinning the exact flagged token, e.g. ULC001's string literal — it
 * survives lines where the same text appears more than once), then fall back
 * to fix metadata / the issue's token / the message-quoted token (which always
 * hit the FIRST occurrence).
 */
export function issueNarrowRange(
  lineText: string,
  issue: { col?: number; end_col?: number; fix?: NarrowFix; message: string; token?: string | null }
): [number, number] | null {
  if (issue.col != null && issue.end_col != null && issue.col < issue.end_col) {
    return [
      Math.max(0, Math.min(issue.col, lineText.length)),
      Math.max(issue.col, Math.min(issue.end_col, lineText.length)),
    ];
  }
  return narrowRange(lineText, issue.fix, issue.message, issue.token);
}
