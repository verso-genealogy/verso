package com.genealogy.dsllint.lint

import com.genealogy.dsllint.settings.DslLintSettings
import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.util.Key
import java.util.Locale
import java.util.concurrent.atomic.AtomicLong

/**
 * Opt-in timing telemetry for the lint pipeline, used to attribute the
 * "slow to reflect fixed findings" latency to the ExternalAnnotator pass nature
 * rather than to plugin work. Enabled via Settings → DSL Lint → "Log lint timing".
 *
 * Decomposition logged per pass (correlation id `pass=N`):
 *   G = edit → collectInformation start  (the platform deferral; the headline)
 *   D = doAnnotate duration (incl. dsllint.py subprocess)
 *   A = apply duration (EDT annotation build)
 *
 * When the toggle is off, [enabled] short-circuits and nothing is logged or
 * recorded — the only cost is a boolean read.
 */
object DslLintTiming {
    /** Wall-clock (nanoTime) of the last edit to a document; set by [DslLintEditTracker]. */
    val LAST_EDIT_NANOS: Key<Long> = Key.create("dsllint.lastEditNanos")

    private val LOG = Logger.getInstance("com.genealogy.dsllint.timing")
    private val passSeq = AtomicLong()

    /** Cheap per-event counters; aggregated from logs during analysis. */
    val collectCount = AtomicLong()
    val doAnnotateStartCount = AtomicLong()
    val doAnnotateDoneCount = AtomicLong()
    val cancelCount = AtomicLong()

    fun enabled(): Boolean = DslLintSettings.getInstance().debugTiming

    fun nextPassId(): Long = passSeq.incrementAndGet()

    fun log(message: String) {
        if (enabled()) LOG.info("[dsllint-timing] $message")
    }

    /** Format a nanosecond delta as milliseconds with one decimal.
     * Locale.ROOT keeps a '.' decimal separator so logs parse consistently
     * regardless of the IDE/JVM locale. */
    fun ms(startNanos: Long, endNanos: Long): String =
        String.format(Locale.ROOT, "%.1f", (endNanos - startNanos) / 1_000_000.0)
}
