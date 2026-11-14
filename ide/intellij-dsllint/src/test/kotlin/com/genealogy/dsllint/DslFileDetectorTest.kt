package com.genealogy.dsllint

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class DslFileDetectorTest {

    @Test fun detectsBirthFile() {
        assertTrue(DslFileDetector.isDslFile("zamanilovka_births_1790.py"))
    }

    @Test fun detectsMarriageFile() {
        assertTrue(DslFileDetector.isDslFile("zamanilovka_marriages_1791.py"))
    }

    @Test fun detectsDeathFile() {
        assertTrue(DslFileDetector.isDslFile("nizhnyaya_yaichnitsa_deaths_1892.py"))
    }

    @Test fun detectsDivorceFile() {
        assertTrue(DslFileDetector.isDslFile("zamanilovka_divorces_1885.py"))
    }

    @Test fun detectsExternalSourcesFile() {
        assertTrue(DslFileDetector.isDslFile("gorjuhino_external_sources_1915.py"))
        assertTrue(DslFileDetector.isDslFile("nizhnyaya_yaichnitsa_external_sources_1914.py"))
    }

    @Test fun detectsNameListsFile() {
        assertTrue(DslFileDetector.isDslFile("manilovka_name_lists_1917.py"))
    }

    @Test fun detectsConfessionsFile() {
        assertTrue(DslFileDetector.isDslFile("zamanilovka_confessions_1828.py"))
    }

    @Test fun detectsFullPath() {
        assertTrue(DslFileDetector.isDslFile("/some/path/Заманиловка/1790/zamanilovka_births_1790.py"))
    }

    @Test fun rejectsCoreModuleFiles() {
        assertFalse(DslFileDetector.isDslFile("genealogy.py"))
        assertFalse(DslFileDetector.isDslFile("births.py"))
        assertFalse(DslFileDetector.isDslFile("statuses.py"))
    }

    @Test fun rejectsTestFiles() {
        assertFalse(DslFileDetector.isDslFile("test_births.py"))
        assertFalse(DslFileDetector.isDslFile("test_genealogy.py"))
    }

    @Test fun rejectsNonPython() {
        assertFalse(DslFileDetector.isDslFile("births_1790.csv"))
    }

    @Test fun rejectsFilesWithoutYear() {
        assertFalse(DslFileDetector.isDslFile("zamanilovka_births.py"))
    }

    @Test fun detectsCensusWithArchiveSuffix() {
        assertTrue(DslFileDetector.isDslFile("gorjuhino_census_1717_d1.py"))
        assertTrue(DslFileDetector.isDslFile("gorjuhino_census_1850_d2.py"))
        assertTrue(DslFileDetector.isDslFile("sobakevichevo_census_1816_d3_penochkin.py"))
    }

    @Test fun detectsCensusWithFullPath() {
        assertTrue(DslFileDetector.isDslFile("/repo/Горюхино/1717/gorjuhino_census_1717_d1.py"))
    }
}
