package com.genealogy.dsllint

import com.genealogy.dsllint.lint.DslLintDependencies
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DslLintDependenciesTest {

    @Test fun matchesStatusesByBaseName() {
        assertTrue(DslLintDependencies.isDependencyFile("statuses.py"))
    }

    @Test fun matchesStatusesByFullPath() {
        assertTrue(DslLintDependencies.isDependencyFile("/repo/geni/domain/statuses.py"))
    }

    @Test fun matchesStatusesByWindowsPath() {
        assertTrue(DslLintDependencies.isDependencyFile("C:\\repo\\geni\\domain\\statuses.py"))
    }

    @Test fun matchesLocationsByBaseName() {
        assertTrue(DslLintDependencies.isDependencyFile("locations.py"))
    }

    @Test fun matchesLocationsByFullPath() {
        // ULC001 reads it; adding a settlement must clear the warning on open records.
        assertTrue(DslLintDependencies.isDependencyFile("/repo/geni/locations.py"))
    }

    @Test fun matchesLocationsByWindowsPath() {
        assertTrue(DslLintDependencies.isDependencyFile("C:\\repo\\geni\\locations.py"))
    }

    @Test fun matchesTheCorpusPlaces() {
        // ULC001 reads them since 0.1.0 (corpus/places.toml).
        assertTrue(DslLintDependencies.isDependencyFile("/repo/corpus/places.toml"))
    }

    @Test fun matchesTheCorpusEstates() {
        // RTV001/RTV002 read the corpus's landlords and parishes from it.
        assertTrue(DslLintDependencies.isDependencyFile("estates.toml"))
        assertTrue(DslLintDependencies.isDependencyFile("/repo/corpus/estates.toml"))
        assertFalse(DslLintDependencies.isDependencyFile("estates.py"))
    }

    @Test fun matchesCausesOfDeath() {
        // single_line_calls offers these constants in place of a matching literal.
        assertTrue(DslLintDependencies.isDependencyFile("causes_of_death.py"))
        assertTrue(DslLintDependencies.isDependencyFile("/repo/geni/domain/causes_of_death.py"))
        assertTrue(DslLintDependencies.isDependencyFile("C:\\repo\\geni\\domain\\causes_of_death.py"))
    }

    @Test fun matchesMaritalStatus() {
        // MST001 flags a literal that is NOT in this vocabulary.
        assertTrue(DslLintDependencies.isDependencyFile("marital_status.py"))
        assertTrue(DslLintDependencies.isDependencyFile("/repo/geni/domain/marital_status.py"))
        assertTrue(DslLintDependencies.isDependencyFile("C:\\repo\\geni\\domain\\marital_status.py"))
    }

    @Test fun matchesTheMaritalStatusCheckItself() {
        // Base-name matching is loose on purpose: the linter shares its base name with
        // the domain vocabulary. Re-linting on either is correct — editing a check also
        // changes what it reports.
        assertTrue(
            DslLintDependencies.isDependencyFile("/repo/geni/linters/checks/marital_status.py"))
    }

    @Test fun rejectsDslRecordFiles() {
        assertFalse(DslLintDependencies.isDependencyFile("zamanilovka_births_1790.py"))
        assertFalse(DslLintDependencies.isDependencyFile("/repo/Заманиловка/1790/zamanilovka_births_1790.py"))
    }

    @Test fun rejectsUnrelatedModule() {
        assertFalse(DslLintDependencies.isDependencyFile("genealogy.py"))
        assertFalse(DslLintDependencies.isDependencyFile("births.py"))
    }

    @Test fun rejectsSimilarlyNamedFile() {
        // Only an exact base-name match counts — not a prefix/suffix.
        assertFalse(DslLintDependencies.isDependencyFile("statuses_extra.py"))
        assertFalse(DslLintDependencies.isDependencyFile("my_statuses.py"))
        assertFalse(DslLintDependencies.isDependencyFile("locations_extra.py"))
        assertFalse(DslLintDependencies.isDependencyFile("familio_locations.py"))
        assertFalse(DslLintDependencies.isDependencyFile("causes_of_death_old.py"))
        assertFalse(DslLintDependencies.isDependencyFile("marital_status_v2.py"))
    }
}
