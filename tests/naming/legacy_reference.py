"""The naming functions as v0.1.26 answered them, over names tables given by path — the reference
the compiled layer is held to (`test_legacy_compile`, `test_lexicon`). Test-only: no module of the
library imports it, and nothing outside tests/ can.

The bodies are v0.1.26's (`naming/names_registry.py` and the five concept modules over it), cut
loose from the workspace and the trace: a `Reference` reads its three files itself, «first row
wins», the second pass over the modern patronymics included. Do not improve them — what they
answer is the point, including where that answer was decided by row order alone.

But for the rules: where the table is silent each function asks `verso.ru.naming.forms` (0.1.27), as
the library does — the rules are not what the compile is held to, and are held on their own
(`test_forms`).
"""
from __future__ import annotations

import csv
from pathlib import Path

from verso.ru.gender import Gender
from verso.ru.naming import forms


class Reference:
    def __init__(self, names_csv: Path, names_ignore: Path | None = None,
                 patronymics_ignore: Path | None = None) -> None:
        self._index_by_name: dict[str, list[dict[str, str]]] = {}
        self._index_by_old_patronymic_m: dict[str, dict[str, str]] = {}
        self._index_by_old_patronymic_f: dict[str, dict[str, str]] = {}
        self._index_by_genitive: dict[str, str] = {}
        self._index_by_modern_patronymic_m: dict[str, str] = {}
        self._index_by_modern_patronymic_f: dict[str, str] = {}
        self._ignore_names: dict[str, Gender | None] = {}
        self._ignore_patronymics: set[str] = set()
        self._load_names_table(names_csv)
        if names_ignore is not None and names_ignore.is_file():
            with open(names_ignore, encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    name = row.get('Name')
                    gender_str = row.get('Gender', '')
                    if name:
                        self._ignore_names[name] = (
                            Gender.MALE if gender_str == 'М' else
                            Gender.FEMALE if gender_str == 'Ж' else
                            None
                        )
        if patronymics_ignore is not None and patronymics_ignore.is_file():
            with open(patronymics_ignore, encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    p = row.get('Patronymic')
                    if p:
                        self._ignore_patronymics.add(p)

    def _load_names_table(self, csv_path: Path) -> None:
        with open(csv_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                name = row.get('Имя')
                if name:
                    self._index_by_name.setdefault(name, []).append(row)
                pat_m = row.get('Отчество старое М')
                if pat_m:
                    self._index_by_old_patronymic_m.setdefault(pat_m, row)
                pat_f = row.get('Отчество старое Ж')
                if pat_f:
                    self._index_by_old_patronymic_f.setdefault(pat_f, row)
                genitive = row.get('Родительный падеж')
                if genitive and name and genitive not in self._index_by_genitive:
                    self._index_by_genitive[genitive] = name
                modern_m = row.get('Отчество М')
                old_m = row.get('Отчество старое М')
                if modern_m and old_m and modern_m not in self._index_by_modern_patronymic_m:
                    self._index_by_modern_patronymic_m[modern_m] = old_m
                modern_f = row.get('Отчество Ж')
                old_f = row.get('Отчество старое Ж')
                if modern_f and old_f and modern_f not in self._index_by_modern_patronymic_f:
                    self._index_by_modern_patronymic_f[modern_f] = old_f
        seen_canonical_m = set()
        seen_canonical_f = set()
        with open(csv_path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('Имя-основа'):
                    continue
                modern_m = row.get('Отчество М')
                old_m = row.get('Отчество старое М')
                if modern_m and old_m and modern_m not in seen_canonical_m:
                    self._index_by_modern_patronymic_m[modern_m] = old_m
                    seen_canonical_m.add(modern_m)
                modern_f = row.get('Отчество Ж')
                old_f = row.get('Отчество старое Ж')
                if modern_f and old_f and modern_f not in seen_canonical_f:
                    self._index_by_modern_patronymic_f[modern_f] = old_f
                    seen_canonical_f.add(modern_f)

    # --- names_registry ---

    def is_ignored_name(self, name):
        return name in self._ignore_names

    def ignored_name_gender(self, name):
        return self._ignore_names.get(name)

    def is_ignored_patronymic(self, patronymic):
        return patronymic in self._ignore_patronymics

    def _find_name_in_table(self, name):
        if not name:
            return []
        return self._index_by_name.get(name, [])

    def _find_old_patronymic_in_table(self, old_patronymic):
        if not old_patronymic:
            return None, None
        row = self._index_by_old_patronymic_m.get(old_patronymic)
        if row:
            return row, Gender.MALE
        row = self._index_by_old_patronymic_f.get(old_patronymic)
        if row:
            return row, Gender.FEMALE
        return None, None

    def _find_full_patronymic_in_table(self, patronymic):
        if not patronymic:
            return None, None
        p = patronymic
        old = self.find_old_patronymic_by_modern(p)
        if old:
            return self._find_old_patronymic_in_table(old)
        if p.endswith(('ович', 'евич')):
            return self._find_old_patronymic_in_table(p[:-2])
        if p.endswith(('овна', 'евна')):
            return self._find_old_patronymic_in_table(p[:-3] + 'ва')
        return None, None

    def name_from_genitive(self, genitive):
        if not genitive:
            return None
        result = self._index_by_genitive.get(genitive)
        return result if result else None

    def genitive_from_name(self, name):
        rows = self._find_name_in_table(name)
        if not rows:
            return None
        candidates = [g for g in (r.get('Родительный падеж') for r in rows) if g]
        if not candidates:
            return None
        stem = name[:-1]
        for g in candidates:
            if g.startswith(stem):
                return g
        folded_stem = stem.replace('ё', 'е')
        for g in candidates:
            if g.replace('ё', 'е').startswith(folded_stem):
                return stem + g[len(stem):]
        return candidates[0]

    def find_old_patronymic_by_modern(self, modern_patronymic):
        if not modern_patronymic:
            return None
        old = self._index_by_modern_patronymic_m.get(modern_patronymic)
        if old:
            return old
        old = self._index_by_modern_patronymic_f.get(modern_patronymic)
        if old:
            return old
        return None

    def father_name_for_patronymic(self, patronymic):
        if not patronymic or '?' in patronymic:
            return None
        row, _ = self._find_old_patronymic_in_table(patronymic)
        if row is None:
            row, _ = self._find_full_patronymic_in_table(patronymic)
        if row is None:
            return None
        return row.get('Имя-основа') or row.get('Имя') or None

    def matching_base(self, name, gender=None):
        if not name or '?' in name:
            return name or ""
        rows = self._find_name_in_table(name)
        if gender is not None:
            pol = 'М' if gender == Gender.MALE else 'Ж'
            rows = [r for r in rows if r.get('Пол') == pol]
        elif len({r.get('Пол') for r in rows}) > 1:
            return name
        bases = {r['Имя-основа'] for r in rows if r.get('Имя-основа')}
        if len(bases) == 1:
            return bases.pop()
        return name

    # --- orthography ---

    def canonicalize_name(self, name, gender=None):
        if not name or '?' in name:
            return name or ""
        rows = self._find_name_in_table(name)
        if gender is not None:
            pol = 'М' if gender == Gender.MALE else 'Ж'
            rows = [r for r in rows if r.get('Пол') == pol]
        if rows:
            if gender is None and len(rows) > 1:
                for r in rows:
                    if not r.get('Имя-основа'):
                        main_name = r.get('Имя')
                        if main_name:
                            return main_name
            canonical = rows[0].get('Имя-основа')
            if canonical:
                return canonical
            main_name = rows[0].get('Имя')
            if main_name:
                return main_name
        return name

    def canonicalize_patronymic(self, patronymic):
        if not patronymic:
            return ""
        p = patronymic
        if '?' in p:
            return p
        row, detected_gender = self._find_old_patronymic_in_table(p)
        if row and detected_gender:
            col = 'Отчество М' if detected_gender == Gender.MALE else 'Отчество Ж'
            modern = row.get(col)
            if modern:
                return modern
        full_row, full_gender = self._find_full_patronymic_in_table(p)
        if full_row and full_gender:
            col = 'Отчество М' if full_gender == Gender.MALE else 'Отчество Ж'
            modern = full_row.get(col)
            if modern:
                return modern
        if p.endswith(('ович', 'евич', 'ич')):
            return p
        if p.endswith(('овна', 'евна', 'ична', 'ишна')):
            return p
        if row is None and not self.is_ignored_patronymic(patronymic):
            raise ValueError(f"Cannot canonicalize patronymic '{patronymic}': not found in names table.")
        modern = forms.modern_from_old(p)
        return modern if modern is not None else p

    # --- patronymics ---

    def derive_patronymic(self, father_name, child_gender):
        if not father_name:
            return ""
        name = father_name
        if '?' in name:
            return "?"
        rows = self._find_name_in_table(name)
        if rows:
            col = 'Отчество М' if child_gender == Gender.MALE else 'Отчество Ж'
            patronymic = rows[0].get(col)
            if patronymic:
                return patronymic
        return forms.modern_patronymic(name, child_gender)

    def derive_old_patronymic(self, father_name, child_gender):
        if not father_name or '?' in father_name:
            return ""
        rows = self._find_name_in_table(father_name)
        if rows:
            col = 'Отчество старое М' if child_gender == Gender.MALE else 'Отчество старое Ж'
            old_form = rows[0].get(col)
            if old_form:
                return old_form
        canonical = self.derive_patronymic(father_name, child_gender)
        if canonical:
            old = self.find_old_patronymic_by_modern(canonical)
            if old:
                return old
        return "" if rows or self.is_ignored_name(father_name) else forms.old_patronymic(father_name, child_gender)

    # --- gender_inference ---

    def get_gender_from_name(self, name):
        if not name or '?' in name:
            return None
        if self.is_ignored_name(name):
            return self.ignored_name_gender(name)
        rows = self._find_name_in_table(name)
        if not rows:
            return None
        genders = {row.get('Пол') for row in rows}
        if genders == {'М'}:
            return Gender.MALE
        elif genders == {'Ж'}:
            return Gender.FEMALE
        return None

    def get_gender_from_old_patronymic(self, old_patronymic):
        _, detected_gender = self._find_old_patronymic_in_table(old_patronymic)
        if detected_gender is None:
            _, detected_gender = self._find_full_patronymic_in_table(old_patronymic)
        return detected_gender

    # --- validation ---

    def validate_first_name(self, name):
        if not name or '?' in name:
            return True
        if self.is_ignored_name(name):
            return True
        rows = self._find_name_in_table(name)
        return len(rows) > 0

    def validate_old_patronymic(self, patronymic, accept_full=False):
        if not patronymic or '?' in patronymic:
            return True
        row, _ = self._find_old_patronymic_in_table(patronymic)
        if row is not None:
            return True
        if accept_full:
            full_row, _ = self._find_full_patronymic_in_table(patronymic)
            if full_row is not None:
                return True
        return self.is_ignored_patronymic(patronymic)

    # --- genitive ---

    def genitive_given_name(self, name, gender=None):
        if not name:
            return ""
        from_table = self.genitive_from_name(name)
        if from_table:
            return from_table
        return forms.genitive(name, gender)

    # --- tree_conflicts (consolidation), the two folds it read rows by ---

    def tree_conflicts_given(self, name):
        rows = self._find_name_in_table(name)
        bases = {r.get("Имя-основа") or r.get("Имя") for r in rows}
        return sorted(b for b in bases if b)[0] if bases else name

    def tree_conflicts_patronymic(self, patronymic):
        row, _ = self._find_full_patronymic_in_table(patronymic)
        if not row:
            return patronymic
        return row.get("Отчество Ж") or row.get("Отчество М") or patronymic
