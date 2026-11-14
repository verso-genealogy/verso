import * as path from "path";

/**
 * Check if a file is a genealogy DSL file by its filename pattern.
 * DSL files match: <village>_<type>_<year>[_<archive_suffix>...].py
 * where type is births, marriages, deaths, divorces, census,
 * confessions, external_sources, or name_lists.
 * Census files always carry an archive-case suffix after the year
 * (e.g. gorjuhino_census_1717_d1.py); the other record types
 * stop at the year (e.g. zamanilovka_births_1790.py,
 * gorjuhino_external_sources_1915.py, manilovka_name_lists_1917.py,
 * zamanilovka_confessions_1828.py).
 */
export function isDslFile(fileName: string): boolean {
  const base = path.basename(fileName);
  return /^[a-z_]+_(births|marriages|deaths|divorces|census|confessions|external_sources|name_lists)_\d{4}(?:_[\w-]+)*\.py$/.test(
    base,
  );
}
