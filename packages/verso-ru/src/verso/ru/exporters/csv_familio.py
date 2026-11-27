from __future__ import annotations

import os
from abc import abstractmethod
from collections.abc import Collection, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from verso.core.ratchet import unreviewed
from verso.ru.ages import split_age as _split_age
from verso.ru.domain import Person, Side
from verso.ru.domain.event_date import date_text
from verso.ru.exporters.base import CsvTable, RecordsExporter, write_table
from verso.ru.relationship import Relationship

if TYPE_CHECKING:
    from verso.ru.dsl.records.marriages import Marriage


class FamilioCsvExporter(RecordsExporter):
    """An exporter of a familio CSV: the table it builds of a record set (`table`), and the file of it."""

    @abstractmethod
    def table(self, record_set: Any, /, records: Sequence[Any] | None = None) -> CsvTable:
        """The CSV of `record_set` as a table, nothing written: every record, or `records` in their order."""

    def export(self, record_set: Any, /, target_dir: str | Path | None = None) -> str:
        """The table written into `target_dir` (the current directory without one), said as the exporters
        always said it; the file's path."""
        filename = write_table(self.table(record_set), os.getcwd() if target_dir is None else str(target_dir))
        print(f"Generated {filename}")
        return filename


def _v(val):
    """Convert None to empty string for CSV output."""
    return val if val is not None else ""


def _registered(day, month, year) -> str | None:
    """A civil book's second date, said in the comment: Familio's CSV has no column for a
    registration, and its christening and burial columns would claim an event that never was.
    A day not written is no date — the month is only the section's."""
    if day is None:
        return None
    return f"зарегистрировано {day}.{_v(month) or '?'}.{year}"


def parent_ages_text(record) -> str:
    """The parents' ages an act states, said in the comment: Familio's CSV has no column for them.
    Written as the DSL has them (verbatim, no `format_age`), so the line repeats the prose the
    ages used to be written in: «отцу 31, матери 30», «отцу 31», «матери 30», or «» without fields."""
    said = [f"{who} {age}" for who, age in (("отцу", getattr(record, "father_age", None)),
                                           ("матери", getattr(record, "mother_age", None)))
            if age is not None and age != ""]
    return ", ".join(said)


def _mk_orig_name(p):
    """Build a book-level `name patr [last_name]` string for one Person.

    Includes `last_name` when `last_name_in_book=True` (the default) —
    reflects what the book's ФИО actually recorded. When the DSL marks
    `last_name_in_book=False`, the surname is known from a separate
    source but was NOT in the book, so drop it.

    Returns the empty string when the person has no name at all.
    """
    if p is None:
        return ""
    parts = [p.name_orig, p.patr_orig]
    if getattr(p, "last_name_in_book", True):
        parts.append(p.last_name)
    return " ".join(x for x in parts if x).strip()


class BirthRecordsCsvFamilioExporter(FamilioCsvExporter):
    def table(self, birth_records: Any, /, records: Sequence[Any] | None = None) -> CsvTable:
        """The CSV of `birth_records` as a table, nothing written: every record, or `records` in their order."""
        return self._table(birth_records, birth_records.year, birth_records.records if records is None else records)

    @staticmethod
    def _relative_cols(rel):
        """Return 6 CSV columns for a birth relative (or 6 empty strings if None)."""
        if rel is None:
            return ["", "", "", "", "", ""]
        p = rel.person
        return [
            rel.relationship_ref or "",                      # Чей родственник
            str(rel.relationship) if rel.relationship else "",  # Родство
            p.status if p else "",                           # Статус
            (p.residence or "") if p else "",                # Н.П.
            "",                                               # person_location
            p.get_fio() if p else "",                        # ФИО (совр.)
        ]

    def _table(self, birth_records, year, records) -> CsvTable:
        name = f"{birth_records.village}_{year}_births_familio.csv"
        headers = [
            "№ п/п",
            "Архив",
            "Фонд",
            "Опись",
            "Дело",
            "Лист",
            "Н.П. события",
            "full_location",
            "Церковь / Приход",
            "Событие",
            "№ записи",
            "Пол",
            "Рожд. День",
            "Рожд. Месяц",
            "Рожд. Год",
            "Крещ. День",
            "Крещ. Месяц",
            "Крещ. Год",
            "Имя реб. (совр. орф.)",
            "Имя реб. (совр.)",
            "Отец: Н.П.",
            "person_location",
            "Отец: Статус",
            "Отец: Фамилия",
            "Отец: Фамилия 2",
            "Отец: Имя (совр. орф.)",
            "Отец: Отчество (совр. орф.)",
            "Отец: Имя (совр.)",
            "Отец: Отчество (совр.)",
            "Мать: Статус",
            "Мать: Фамилия",
            "Мать: Имя (совр. орф.)",
            "Мать: Отчество (совр. орф.)",
            "Мать: Имя (совр.)",
            "Мать: Отчество (совр.)",
            "Восприемник 1: Статус",
            "Восприемник 1: Н.П.",
            "Восприемник 1: person_location",
            "Восприемник 1: Имя (совр. орф.)",
            "Восприемник 1: Отчество (совр. орф.)",
            "Восприемник 1: Имя (совр.)",
            "Восприемник 1: Отчество (совр.)",
            "Восприемник 1: ФИО (совр.)",
            "Восприемник 2: Статус",
            "Восприемник 2: Н.П.",
            "Восприемник 2: person_location",
            "Восприемник 2: Имя (совр. орф.)",
            "Восприемник 2: Отчество (совр. орф.)",
            "Восприемник 2: Имя (совр.)",
            "Восприемник 2: Отчество (совр.)",
            "Восприемник 2: ФИО (совр.)",
            "Восприемник 3: Статус",
            "Восприемник 3: Н.П.",
            "Восприемник 3: person_location",
            "Восприемник 3: ФИО (совр.)",
            "Восприемник 4: Статус",
            "Восприемник 4: Н.П.",
            "Восприемник 4: person_location",
            "Восприемник 4: ФИО (совр.)",
            "Родственник 1: Чей родственник",
            "Родственник 1: Родство",
            "Родственник 1: Статус",
            "Родственник 1: Н.П.",
            "Родственник 1: person_location",
            "Родственник 1: ФИО (совр.)",
            "Родственник 2: Чей родственник",
            "Родственник 2: Родство",
            "Родственник 2: Статус",
            "Родственник 2: Н.П.",
            "Родственник 2: person_location",
            "Родственник 2: ФИО (совр.)",
            "Священник: Статус",
            "Священник: ФИО (совр.)",
            "Церковь (если иной приход)",
            "Н.П. церкви другого прихода",
            "Дьякон: Статус",
            "Дьякон: ФИО (совр.)",
            "Псаломщик: Статус",
            "Псаломщик: ФИО (совр.)",
            "Комментарий",
            "Имена в оригинале"
        ]

        rows: list[list[object]] = []
        for r in records:
            orig_names = []
            if r.child: orig_names.append(r.child.name_orig)
            if r.father: orig_names.append(_mk_orig_name(r.father))
            if r.mother: orig_names.append(_mk_orig_name(r.mother))
            if r.god_parent1: orig_names.append(_mk_orig_name(r.god_parent1))
            if r.god_parent2: orig_names.append(_mk_orig_name(r.god_parent2))
            orig_names_str = "; ".join(filter(None, orig_names))

            if orig_names_str:
                orig_names_str = "Имена в МК: " + orig_names_str

            # Logic for comments
            comments = []
            if r.comment:
                comments.append(r.comment)
            if parent_ages_text(r):
                comments.append(parent_ages_text(r))
            # Add comment from each person
            for person in [r.child, r.father, r.mother, r.god_parent1, r.god_parent2,
                           r.priest, r.deacon, r.dyachok, r.sexton]:
                if person and person.comment:
                    comments.append(person.comment)
            civil = getattr(birth_records, "civil", False)
            record_year = r.year if r.year is not None else year
            registered = (_registered(r.k_day, r.k_month, getattr(r, "k_year", None) or record_year)
                          if civil else None)
            if registered:
                comments.append(registered)
            final_comment = "; ".join(comments)

            # Late/adult christening: no recorded birth date. Leave the
            # Рожд. День/Месяц columns blank and put a circa birth year
            # (christening year − age) in Рожд. Год; the Крещ. columns
            # keep the actual christening date.
            christening_age = getattr(r, "christening_age", None)
            if christening_age is not None:
                b_day_col = ""
                b_month_col = ""
                b_year_col = record_year - christening_age
            else:
                b_day_col = r.b_day
                b_month_col = _v(r.b_month)
                b_year_col = record_year

            row = [
                "",  # 1. № п/п
                birth_records.archive,  # 2. Архив
                birth_records.fund,  # 3. Фонд
                r.inventory or birth_records.inventory,  # 4. Опись
                r.case or birth_records.case,  # 5. Дело
                r.page if r.page else "",  # 6. Лист
                birth_records.village,  # 7. Н.П. события
                "",  # 8. full_location
                birth_records.church,  # 9. Церковь / Приход
                "рождение",  # 10. Событие
                r.record_num,  # 11. № записи
                r.gender,  # 12. Пол
                b_day_col,  # 13. Рожд. День
                b_month_col,  # 14. Рожд. Месяц
                b_year_col,  # 15. Рожд. Год
                "" if civil else r.k_day,  # 16. Крещ. День (a civil book christens no one)
                "" if civil else _v(r.k_month),  # 17. Крещ. Месяц
                "" if civil else record_year,  # 18. Крещ. Год
                r.child.name_modern if r.child else "",  # 19. Имя реб. (совр. орф.)
                r.child.get_canonical_name() if r.child else "",  # 20. Имя реб. (совр.)
                r.father.residence if r.father else "",  # 21. Отец: Н.П.
                "",  # 22. person_location
                r.father.status if r.father else "",  # 23. Отец: Статус
                r.father.last_name_modern if r.father else "",  # 24. Отец: Фамилия
                "",  # 25. Отец: Фамилия 2
                r.father.name_modern if r.father else "",  # 26. Отец: Имя (совр. орф.)
                r.father.patr_old if r.father else "",  # 27. Отец: Отчество (совр. орф.)
                r.father.get_canonical_name() if r.father else "",  # 28. Отец: Имя (совр.)
                r.father.patr_modern if r.father else "",  # 29. Отец: Отчество (совр.)
                r.mother.status if r.mother else "",  # 30. Мать: Статус
                r.mother.last_name_modern if r.mother else "",  # 31. Мать: Фамилия
                r.mother.name_modern if r.mother else "",  # 32. Мать: Имя (совр. орф.)
                r.mother.patr_old if r.mother else "",  # 33. Мать: Отчество (совр. орф.)
                r.mother.get_canonical_name() if r.mother else "",  # 34. Мать: Имя (совр.)
                r.mother.patr_modern if r.mother else "",  # 35. Мать: Отчество (совр.)
                r.god_parent1.status if r.god_parent1 else "",  # 36. Восприемник 1: Статус
                r.god_parent1.residence if r.god_parent1 else "",  # 37. Восприемник 1: Н.П.
                "",  # 38. Восприемник 1: person_location
                r.god_parent1.name_modern if r.god_parent1 else "",  # 39. Восприемник 1: Имя (совр. орф.)
                r.god_parent1.patr_old if r.god_parent1 else "",  # 40. Восприемник 1: Отчество (совр. орф.)
                r.god_parent1.get_canonical_name() if r.god_parent1 else "",  # 41. Восприемник 1: Имя (совр.)
                r.god_parent1.patr_modern if r.god_parent1 else "",
                # 42. Восприемник 1: Отчество (совр.)
                r.god_parent1.get_fio() if r.god_parent1 else "",  # 43. Восприемник 1: ФИО (совр.)
                r.god_parent2.status if r.god_parent2 else "",  # 44. Восприемник 2: Статус
                r.god_parent2.residence if r.god_parent2 else "",  # 45. Восприемник 2: Н.П.
                "",  # 46. Восприемник 2: person_location
                r.god_parent2.name_modern if r.god_parent2 else "",  # 47. Восприемник 2: Имя (совр. орф.)
                r.god_parent2.patr_old if r.god_parent2 else "",  # 48. Восприемник 2: Отчество (совр. орф.)
                r.god_parent2.get_canonical_name() if r.god_parent2 else "",  # 49. Восприемник 2: Имя (совр.)
                r.god_parent2.patr_modern if r.god_parent2 else "",
                # 50. Восприемник 2: Отчество (совр.)
                r.god_parent2.get_fio() if r.god_parent2 else "",  # 51. Восприемник 2: ФИО (совр.)
                "",  # 52. Восприемник 3: Статус
                "",  # 53. Восприемник 3: Н.П.
                "",  # 54. Восприемник 3: person_location
                "",  # 55. Восприемник 3: ФИО (совр.)
                "",  # 56. Восприемник 4: Статус
                "",  # 57. Восприемник 4: Н.П.
                "",  # 58. Восприемник 4: person_location
                "",  # 59. Восприемник 4: ФИО (совр.)
                *self._relative_cols(r.relatives[0] if r.relatives else None),       # 60-65. Родственник 1
                *self._relative_cols(r.relatives[1] if len(r.relatives) > 1 else None),  # 66-71. Родственник 2
                r.priest.status if r.priest else "",  # 72. Священник: Статус
                r.priest.get_fio() if r.priest else "",  # 73. Священник: ФИО (совр.)
                "",  # 74. Церковь (если иной приход)
                "",  # 75. Н.П. церкви другого прихода
                r.deacon.status if r.deacon else "",  # 76. Дьякон: Статус
                r.deacon.get_fio() if r.deacon else "",  # 77. Дьякон: ФИО (совр.)
                r.dyachok.status if r.dyachok else "",  # 78. Псаломщик: Статус
                r.dyachok.get_fio() if r.dyachok else "",  # 79. Псаломщик: ФИО (совр.)
                final_comment,  # 80. Комментарий
                orig_names_str  # 81. Имена в оригинале
            ]
            rows.append(row)
        return CsvTable(name, headers, rows)


def _witness_columns(r: Marriage) -> list[Person | None]:
    """The six «Поручитель N» column groups of a marriage, in CSV order.

    The Familio справочник template reads CSV sureties 1–3 as «по жениху» and
    4–6 as «по невесте» (`familio_template.SRC_MARRIAGES`). A record that
    declares no side keeps its slot order, as before sides existed. Once any
    witness declares one, the groom's go first into 1–3 and the bride's into
    4–6, each side in slot order; a witness without a side takes the next free
    place, and a side with more than three (WSD006) spills into the free places
    of the other rather than being dropped.
    """
    slots = r.witness_sides()
    positional: list[Person | None] = [None] * 6
    for n, p, _ in slots:
        positional[n - 1] = p
    if all(side is None for _, _, side in slots):
        return positional
    out: list[Person | None] = [None] * 6
    groom = [p for _, p, side in slots if side is Side.GROOM]
    bride = [p for _, p, side in slots if side is Side.BRIDE]
    rest = [p for _, p, side in slots if side is None]
    for i, p in enumerate(groom[:3]):
        out[i] = p
    for i, p in enumerate(bride[:3]):
        out[3 + i] = p
    for p in groom[3:] + bride[3:] + rest:
        out[out.index(None)] = p
    return out


def _short_witness(p: Person | None) -> tuple[object, object, str, str]:
    """Статус, Н.П., person_location, ФИО (совр.) — the 4-column surety group."""
    if p is None:
        return "", "", "", ""
    return p.status or "", p.residence or "", "", p.get_fio()


class MarriageRecordsCsvFamilioExporter(FamilioCsvExporter):
    def table(self, marriage_records: Any, /, records: Sequence[Any] | None = None) -> CsvTable:
        """The CSV of `marriage_records` as a table, nothing written: every record, or `records` in their order."""
        chosen: Sequence[Any] = marriage_records.records if records is None else records
        name = f"{marriage_records.village}_{marriage_records.year}_marriages_familio.csv"
        headers = [
            "№ п/п",
            "Архив",
            "Фонд",
            "Опись",
            "Дело",
            "Лист",
            "Н.П. события",
            "full_location",
            "Церковь / Приход",
            "Событие",
            "№ записи",
            "День",
            "Месяц",
            "Год",
            "Жених: Н.П.",
            "Жених: person_location",
            "Жених: Статус",
            "Жених: Фамилия",
            "Жених: Фамилия 2",
            "Жених: Имя (совр. орф.)",
            "Жених: Отчество (совр. орф.)",
            "Жених: Имя (совр.)",
            "Жених: Отчество (совр.)",
            "Жених: Номер брака",
            "Жених: Лет",
            "Жених: Месяцев",
            "Жених: Недель",
            "Жених: Дней",
            "Отец жениха: Н.П.",
            "Отец жениха: person_location",
            "Отец жениха: Статус",
            "Отец жениха: Фамилия",
            "Отец жениха: Фамилия 2",
            "Отец жениха: Имя (совр.)",
            "Отец жениха: Отчество (совр.)",
            "Невеста: Н.П.",
            "Невеста: person_location",
            "Невеста: Статус",
            "Невеста: Фамилия",
            "Невеста: Имя (совр. орф.)",
            "Невеста: Отчество (совр. орф.)",
            "Невеста: Имя (совр.)",
            "Невеста: Отчество (совр.)",
            "Невеста: Номер брака",
            "Невеста: Лет",
            "Невеста: Месяцев",
            "Невеста: Недель",
            "Невеста: Дней",
            "Отец невесты: Н.П.",
            "Отец невесты: person_location",
            "Отец невесты: Статус",
            "Отец невесты: Фамилия",
            "Отец невесты: Фамилия 2",
            "Отец невесты: Имя (совр.)",
            "Отец невесты: Отчество (совр.)",
            "Поручитель 1: Статус",
            "Поручитель 1: Н.П.",
            "Поручитель 1: person_location",
            "Поручитель 1: Фамилия",
            "Поручитель 1: Имя (совр. орф)",
            "Поручитель 1: Отчество (совр. орф)",
            "Поручитель 1: Имя (совр.)",
            "Поручитель 1: Отчество (совр.)",
            "Поручитель 1: ФИО (совр.)",
            "Поручитель 2: Статус",
            "Поручитель 2: Н.П.",
            "Поручитель 2: person_location",
            "Поручитель 2: Фамилия",
            "Поручитель 2: Имя (совр. орф)",
            "Поручитель 2: Отчество (совр. орф)",
            "Поручитель 2: Имя (совр.)",
            "Поручитель 2: Отчество (совр.)",
            "Поручитель 2: ФИО (совр.)",
            "Поручитель 3: Статус",
            "Поручитель 3: Н.П.",
            "Поручитель 3: person_location",
            "Поручитель 3: ФИО (совр.)",
            "Поручитель 4: Статус",
            "Поручитель 4: Н.П.",
            "Поручитель 4: person_location",
            "Поручитель 4: ФИО (совр.)",
            "Поручитель 5: Статус",
            "Поручитель 5: Н.П.",
            "Поручитель 5: person_location",
            "Поручитель 5: ФИО (совр.)",
            "Поручитель 6: Статус",
            "Поручитель 6: Н.П.",
            "Поручитель 6: person_location",
            "Поручитель 6: ФИО (совр.)",
            "Родственник поручителя 1: Номер поручителя",
            "Родственник поручителя 1: Родство",
            "Родственник поручителя 1: Статус",
            "Родственник поручителя 1: Н.П.",
            "Родственник поручителя 1: person_location",
            "Родственник поручителя 1: ФИО (совр.)",
            "Родственник поручителя 2: Номер поручителя",
            "Родственник поручителя 2: Родство",
            "Родственник поручителя 2: Статус",
            "Родственник поручителя 2: Н.П.",
            "Родственник поручителя 2: person_location",
            "Родственник поручителя 2: ФИО (совр.)",
            "Священник: Статус",
            "Священник: ФИО (совр.)",
            "Церковь (если иной приход)",
            "Н.П. церкви другого прихода",
            "Дьякон: Статус",
            "Дьякон: ФИО (совр.)",
            "Псаломщик: Статус",
            "Псаломщик: ФИО (совр.)",
            "Комментарий",
            "Имена в оригинале"
        ]

        rows: list[list[object]] = []
        for r in chosen:
            orig_names = []
            for p in (r.groom, r.bride, r.witness1, r.witness2,
                      r.witness3, r.witness4, r.witness5, r.witness6):
                if p:
                    orig_names.append(_mk_orig_name(p))
            for rel in r.relatives:
                if rel.person:
                    orig_names.append(_mk_orig_name(rel.person))
            orig_names_str = "; ".join(filter(None, orig_names))

            if orig_names_str:
                orig_names_str = "Имена в МК: " + orig_names_str

            # Find father relatives for groom and bride
            groom_father = None
            bride_father = None
            comment_relatives = []
            for rel in r.relatives:
                if rel.relationship == Relationship.FATHER and rel.relationship_ref == "жених":
                    groom_father = rel.person
                elif rel.relationship == Relationship.FATHER and rel.relationship_ref == "невеста":
                    bride_father = rel.person
                else:
                    # Non-father relatives go to comment
                    p = rel.person
                    ref = rel.relationship_ref or ""
                    parts = [p.status, p.get_fio()]
                    desc = " ".join(filter(None, parts))
                    comment_relatives.append(f"{rel.relationship} {ref}: {desc}".strip())

            # Build comments
            comments = []
            if r.comment:
                comments.append(r.comment)
            for cp in [r.groom, r.bride, r.witness1, r.witness2, r.witness3, r.witness4,
                       r.witness5, r.witness6,
                       r.priest, r.deacon, r.dyachok, r.sexton]:
                if cp is None:
                    continue
                side = getattr(cp, "side", None)
                words = [f"поручитель {side}"] if side is not None else []
                if cp.comment:
                    words.append(cp.comment)
                if words:
                    comments.append("; ".join(words))
            w = _witness_columns(r)
            for rel in r.relatives:
                if rel.person and rel.person.comment:
                    comments.append(rel.person.comment)
            comments.extend(comment_relatives)
            final_comment = "; ".join(comments)

            row = [
                "",  # 1. № п/п (empty)
                r.archive or marriage_records.archive,  # 2. Архив
                r.fund or marriage_records.fund,  # 3. Фонд
                r.inventory or marriage_records.inventory,  # 4. Опись
                r.case or marriage_records.case,  # 5. Дело
                r.page if r.page else "",  # 6. Лист
                getattr(r, "village", None) or marriage_records.village,  # 7. Н.П. события
                "",  # 8. full_location
                r.church or marriage_records.church,  # 9. Церковь / Приход
                "брак",  # 10. Событие
                r.record_num,  # 11. № записи
                r.w_day,  # 12. День
                _v(r.w_month),  # 13. Месяц
                (r.year if r.year is not None else marriage_records.year),  # 14. Год
                r.groom.residence if r.groom else "",  # 15. Жених: Н.П.
                "",  # 16. Жених: person_location
                r.groom.status if r.groom else "",  # 17. Жених: Статус
                r.groom.last_name_modern if r.groom else "",  # 18. Жених: Фамилия
                "",  # 19. Жених: Фамилия 2
                r.groom.name_modern if r.groom else "",  # 20. Жених: Имя (совр. орф.)
                r.groom.patr_old if r.groom else "",  # 21. Жених: Отчество (совр. орф.)
                r.groom.get_canonical_name() if r.groom else "",  # 22. Жених: Имя (совр.)
                r.groom.patr_modern if r.groom else "",  # 23. Жених: Отчество (совр.)
                r.groom_marriage_num if r.groom_marriage_num else "",  # 24. Жених: Номер брака
                *_split_age(r.groom_age),  # 25–28. Жених: Лет, Месяцев, Недель, Дней
                groom_father.residence if groom_father else "",  # 29. Отец жениха: Н.П.
                "",  # 30. Отец жениха: person_location
                groom_father.status if groom_father else "",  # 31. Отец жениха: Статус
                groom_father.last_name_modern if groom_father else "",  # 32. Отец жениха: Фамилия
                "",  # 33. Отец жениха: Фамилия 2
                groom_father.get_canonical_name() if groom_father else "",  # 34. Отец жениха: Имя (совр.)
                groom_father.patr_modern if groom_father else "",  # 35. Отец жениха: Отчество (совр.)
                r.bride.residence if r.bride else "",  # 36. Невеста: Н.П.
                "",  # 37. Невеста: person_location
                r.bride.status if r.bride else "",  # 38. Невеста: Статус
                r.bride.last_name_modern if r.bride else "",  # 39. Невеста: Фамилия
                r.bride.name_modern if r.bride else "",  # 40. Невеста: Имя (совр. орф.)
                r.bride.patr_old if r.bride else "",  # 41. Невеста: Отчество (совр. орф.)
                r.bride.get_canonical_name() if r.bride else "",  # 42. Невеста: Имя (совр.)
                r.bride.patr_modern if r.bride else "",  # 43. Невеста: Отчество (совр.)
                r.bride_marriage_num if r.bride_marriage_num else "",  # 44. Невеста: Номер брака
                *_split_age(r.bride_age),  # 45–48. Невеста: Лет, Месяцев, Недель, Дней
                bride_father.residence if bride_father else "",  # 49. Отец невесты: Н.П.
                "",  # 50. Отец невесты: person_location
                bride_father.status if bride_father else "",  # 51. Отец невесты: Статус
                bride_father.last_name_modern if bride_father else "",  # 52. Отец невесты: Фамилия
                "",  # 53. Отец невесты: Фамилия 2
                bride_father.get_canonical_name() if bride_father else "",  # 54. Отец невесты: Имя (совр.)
                bride_father.patr_modern if bride_father else "",  # 55. Отец невесты: Отчество (совр.)
                w[0].status if w[0] else "",  # 56. Поручитель 1: Статус
                w[0].residence if w[0] else "",  # 57. Поручитель 1: Н.П.
                "",  # 58. Поручитель 1: person_location
                w[0].last_name_modern if w[0] else "",  # 59. Поручитель 1: Фамилия
                w[0].name_modern if w[0] else "",  # 60. Поручитель 1: Имя (совр. орф)
                w[0].patr_old if w[0] else "",  # 61. Поручитель 1: Отчество (совр. орф)
                w[0].get_canonical_name() if w[0] else "",  # 62. Поручитель 1: Имя (совр.)
                w[0].patr_modern if w[0] else "",  # 63. Поручитель 1: Отчество (совр.)
                w[0].get_fio() if w[0] else "",  # 64. Поручитель 1: ФИО (совр.)
                w[1].status if w[1] else "",  # 65. Поручитель 2: Статус
                w[1].residence if w[1] else "",  # 66. Поручитель 2: Н.П.
                "",  # 67. Поручитель 2: person_location
                w[1].last_name_modern if w[1] else "",  # 68. Поручитель 2: Фамилия
                w[1].name_modern if w[1] else "",  # 69. Поручитель 2: Имя (совр. орф)
                w[1].patr_old if w[1] else "",  # 70. Поручитель 2: Отчество (совр. орф)
                w[1].get_canonical_name() if w[1] else "",  # 71. Поручитель 2: Имя (совр.)
                w[1].patr_modern if w[1] else "",  # 72. Поручитель 2: Отчество (совр.)
                w[1].get_fio() if w[1] else "",  # 73. Поручитель 2: ФИО (совр.)
                *_short_witness(w[2]),  # 74–77. Поручитель 3: Статус, Н.П., person_location, ФИО
                *_short_witness(w[3]),  # 78–81. Поручитель 4
                *_short_witness(w[4]),  # 82–85. Поручитель 5
                *_short_witness(w[5]),  # 86–89. Поручитель 6
                "",  # 90. Родственник поручителя 1: Номер поручителя
                "",  # 91. Родственник поручителя 1: Родство
                "",  # 92. Родственник поручителя 1: Статус
                "",  # 93. Родственник поручителя 1: Н.П.
                "",  # 94. Родственник поручителя 1: person_location
                "",  # 95. Родственник поручителя 1: ФИО (совр.)
                "",  # 96. Родственник поручителя 2: Номер поручителя
                "",  # 97. Родственник поручителя 2: Родство
                "",  # 98. Родственник поручителя 2: Статус
                "",  # 99. Родственник поручителя 2: Н.П.
                "",  # 100. Родственник поручителя 2: person_location
                "",  # 101. Родственник поручителя 2: ФИО (совр.)
                r.priest.status if r.priest else "",  # 102. Священник: Статус
                r.priest.get_fio() if r.priest else "",  # 103. Священник: ФИО (совр.)
                "",  # 104. Церковь (если иной приход)
                "",  # 105. Н.П. церкви другого прихода
                r.deacon.status if r.deacon else "",  # 106. Дьякон: Статус
                r.deacon.get_fio() if r.deacon else "",  # 107. Дьякон: ФИО (совр.)
                r.dyachok.status if r.dyachok else "",  # 108. Псаломщик: Статус
                r.dyachok.get_fio() if r.dyachok else "",  # 109. Псаломщик: ФИО (совр.)
                final_comment,  # 110. Комментарий
                orig_names_str  # 111. Имена в оригинале
            ]
            rows.append(row)
        return CsvTable(name, headers, rows)


class DeathRecordsCsvFamilioExporter(FamilioCsvExporter):
    def table(self, death_records: Any, /, records: Sequence[Any] | None = None) -> CsvTable:
        """The CSV of `death_records` as a table, nothing written: every record, or `records` in their order."""
        return self._table(death_records, death_records.year, death_records.records if records is None else records)

    def _table(self, death_records, year, records) -> CsvTable:
        name = f"{death_records.village}_{year}_deaths_familio.csv"
        headers = [
            "№ п/п", "Архив", "Фонд", "Опись", "Дело", "Лист", "Н.П. события", "full_location",
            "Церковь / Приход", "Событие", "№ записи", "Пол",
            "День", "Месяц", "Год", "День", "Месяц", "Год",  # Death & burial dates
            "Н.П. приписки", "person_location", "статус/чин", "Фамилия", "Фамилия-2",
            "Имя (совр. орф.)", "Отчество (совр. орф.)", "Имя", "Отчество",  # Deceased
            "Лет", "Месяцев", "Недель", "Дней",  # Age
            "родство", "Н.П. приписки", "person_location", "статус/чин", "Фамилия", "Фамилия-2",
            "Имя (совр. орф.)", "Отчество (совр. орф.)", "Имя", "Отчество",  # Relative
            "",  # Cause of death (empty)
            "Имя (совр. орф.)", "Отчество (совр. орф.)", "Имя", "Отчество",  # Witness 1
            "Имя (совр. орф.)", "Отчество (совр. орф.)", "Имя", "Отчество",  # Witness 2
            "статус священника", "ФИО священника", "Церковь - если иной Приход", "Н.П. церкви другого прихода",
            # Confession clergy
            "статус священника", "ФИО священника", "Церковь - если иной Приход", "Н.П. церкви другого прихода",
            # Burial clergy
            "статус дьякона", "ФИО дьякона", "статус псаломщика", "ФИО псаломщика",  # Other clergy
            "",  # Burial location (empty)
            "пометки", "Имена в оригинале"
        ]

        rows: list[list[object]] = []
        for r in records:
            # The record's comment and each person's: a status the catalog keeps as a constant leaves the
            # scribe's words in the person's comment= (В15), and пометки is the CSV's only place for them.
            comments = []
            if r.comment:
                comments.append(r.comment)
            for p in [r.deceased, *(rel.person for rel in r.relatives), r.witness1, r.witness2,
                      r.priest, r.deacon, r.dyachok, r.sexton]:
                if p and p.comment:
                    comments.append(p.comment)

            orig_names = []
            if r.deceased:
                orig_names.append(_mk_orig_name(r.deceased))
            for rel in r.relatives:
                if rel.person:
                    orig_names.append(_mk_orig_name(rel.person))

            orig_names_str = "; ".join(filter(None, orig_names))

            if orig_names_str:
                orig_names_str = "Имена в МК: " + orig_names_str

            witness_names = []
            for p in (r.witness1, r.witness2):
                if p:
                    witness_names.append(_mk_orig_name(p))

            witness_names_str = "; ".join(filter(None, witness_names))

            if witness_names_str:
                witness_names_str = "cвидетели: " + witness_names_str

            civil = getattr(death_records, "civil", False)
            registered = (_registered(r.b_day, r.b_month, r.year if r.year is not None else year)
                          if civil else None)

            # Extra relatives (beyond the first) go to the notes column
            extra_rel_strs = []
            for extra_rel in r.relatives[1:]:
                p = extra_rel.person
                if p:
                    parts = [p.status, p.get_fio()]
                    desc = " ".join(filter(None, parts))
                    rel_str = str(extra_rel.relationship) if extra_rel.relationship else ""
                    extra_rel_strs.append(f"{rel_str}: {desc}".strip(": "))

            row = [
                "",  # 1. № п/п
                r.archive or death_records.archive,  # 2. Архив
                r.fund or death_records.fund,  # 3. Фонд
                r.inventory or death_records.inventory,  # 4. Опись
                r.case or death_records.case,  # 5. Дело
                r.page if r.page else "",  # 6. Лист
                death_records.village,  # 7. Н.П. события
                "",  # 8. full_location
                r.church or death_records.church,  # 9. Церковь / Приход
                "смерть",  # 10. Событие
                r.record_num,  # 11. № записи
                r.gender,  # 12. Пол
                r.d_day,  # 13. День (death)
                _v(r.d_month),  # 14. Месяц (death)
                (r.year if r.year is not None else year),  # 15. Год (death)
                "" if civil else r.b_day,  # 16. День (burial; a civil book buries no one)
                "" if civil else _v(r.b_month),  # 17. Месяц (burial)
                "" if civil else (r.year if r.year is not None else year),  # 18. Год (burial)
                r.deceased.residence if r.deceased else "",  # 19. Н.П. приписки (deceased)
                "",  # 20. person_location
                r.deceased.status if r.deceased else "",  # 21. статус/чин (deceased)
                r.deceased.last_name_modern if r.deceased else "",  # 22. Фамилия (deceased)
                "",  # 23. Фамилия-2
                r.deceased.name_modern if r.deceased else "",  # 24. Имя (совр. орф.) (deceased)
                r.deceased.patr_old if r.deceased else "",  # 25. Отчество (совр. орф.) (deceased)
                r.deceased.get_canonical_name() if r.deceased else "",  # 26. Имя (deceased)
                r.deceased.patr_modern if r.deceased else "",  # 27. Отчество (deceased)
                *_split_age(r.age),  # 28-31: Лет, Месяцев, Недель, Дней
                r.relationship if r.relationship else "",  # 32. родство
                r.relative.residence if r.relative else "",  # 33. Н.П. приписки (relative)
                "",  # 34. person_location
                r.relative.status if r.relative else "",  # 35. статус/чин (relative)
                r.relative.last_name_modern if r.relative else "",  # 36. Фамилия (relative)
                "",  # 37. Фамилия-2
                r.relative.name_modern if r.relative else "",  # 38. Имя (совр. орф.) (relative)
                r.relative.patr_old if r.relative else "",  # 39. Отчество (совр. орф.) (relative)
                r.relative.get_canonical_name() if r.relative else "",  # 40. Имя (relative)
                r.relative.patr_modern if r.relative else "",  # 41. Отчество (relative)
                r.cause_of_death if r.cause_of_death else "",  # 42. Причина смерти
                r.witness1.name_modern if r.witness1 else "",  # 43. Имя (совр. орф.) (witness1)
                r.witness1.patr_old if r.witness1 else "",  # 44. Отчество (совр. орф.) (witness1)
                r.witness1.get_canonical_name() if r.witness1 else "",  # 45. Имя (witness1)
                r.witness1.patr_modern if r.witness1 else "",  # 46. Отчество (witness1)
                r.witness2.name_modern if r.witness2 else "",  # 47. Имя (совр. орф.) (witness2)
                r.witness2.patr_old if r.witness2 else "",  # 48. Отчество (совр. орф.) (witness2)
                r.witness2.get_canonical_name() if r.witness2 else "",  # 49. Имя (witness2)
                r.witness2.patr_modern if r.witness2 else "",  # 50. Отчество (witness2)
                "",  # 51. статус священника (confession clergy)
                "",  # 52. ФИО священника
                "",  # 53. Церковь - если иной Приход
                "",  # 54. Н.П. церкви другого прихода
                r.priest.status if r.priest else "",  # 55. статус священника (burial clergy)
                r.priest.get_fio() if r.priest else "",  # 56. ФИО священника
                "",  # 57. Церковь - если иной Приход
                "",  # 58. Н.П. церкви другого прихода
                r.deacon.status if r.deacon else "",  # 59. статус дьякона
                r.deacon.get_fio() if r.deacon else "",  # 60. ФИО дьякона
                r.dyachok.status if r.dyachok else "",  # 61. статус псаломщика
                r.dyachok.get_fio() if r.dyachok else "",  # 62. ФИО псаломщика
                "",  # 63. Burial location
                "; ".join(filter(None, comments + [witness_names_str] + extra_rel_strs + [registered])),  # 64. пометки
                orig_names_str  # 65. авторский комментарий
            ]
            rows.append(row)
        return CsvTable(name, headers, rows)


class DivorceRecordsCsvFamilioExporter(FamilioCsvExporter):
    def table(self, divorce_records: Any, /, records: Sequence[Any] | None = None) -> CsvTable:
        """The CSV of `divorce_records` as a table, nothing written: every record, or `records` in their order."""
        chosen: Sequence[Any] = divorce_records.records if records is None else records
        name = f"{divorce_records.village}_{divorce_records.year}_divorces_familio.csv"
        headers = [
            "№ п/п",
            "Архив",
            "Фонд",
            "Опись",
            "Дело",
            "Лист",
            "Н.П. события",
            "Событие",
            "№ записи",
            "День",
            "Месяц",
            "Год",
            "Муж: Н.П.",
            "Муж: Фамилия",
            "Муж: Имя (совр.)",
            "Муж: Отчество (совр.)",
            "Муж: Лет",
            "Жена: Н.П.",
            "Жена: Фамилия",
            "Жена: Фамилия (девичья)",
            "Жена: Имя (совр.)",
            "Жена: Отчество (совр.)",
            "Жена: Лет",
            "Дата заключения брака",
            "Дети",
            "Инициатор",
            "Комментарий",
        ]

        rows: list[list[object]] = []
        for r in chosen:
            comments = []
            if r.comment:
                comments.append(r.comment)
            if r.husband and r.husband.comment:
                comments.append(r.husband.comment)
            if r.wife and r.wife.comment:
                comments.append(r.wife.comment)
            final_comment = "; ".join(comments)

            row = [
                "",
                divorce_records.archive,
                divorce_records.fund,
                divorce_records.inventory,
                r.case or divorce_records.case,
                r.page if r.page else "",
                divorce_records.village,
                "развод",
                r.record_num,
                r.d_day,
                _v(r.d_month),
                (r.year if r.year is not None else divorce_records.year),
                r.husband.residence if r.husband else "",
                r.husband.last_name_modern if r.husband else "",
                r.husband.get_canonical_name() if r.husband else "",
                r.husband.patr_modern if r.husband else "",
                r.husband_age if r.husband_age is not None else "",
                r.wife.residence if r.wife else "",
                r.wife.last_name_modern if r.wife else "",
                r.wife.last_name if r.wife else "",
                r.wife.get_canonical_name() if r.wife else "",
                r.wife.patr_modern if r.wife else "",
                r.wife_age if r.wife_age is not None else "",
                date_text(r.marriage_date),
                r.children or "",
                r.initiator or "",
                final_comment,
            ]
            rows.append(row)
        return CsvTable(name, headers, rows)


def _familio_exporters() -> dict[type, FamilioCsvExporter]:
    """The familio exporter of each record set that has one, by the set's class (the DSL imports nothing here)."""
    from verso.ru.dsl.records.births import BirthRecords
    from verso.ru.dsl.records.deaths import DeathRecords
    from verso.ru.dsl.records.divorces import DivorceRecords
    from verso.ru.dsl.records.marriages import MarriageRecords

    return {BirthRecords: BirthRecordsCsvFamilioExporter(), MarriageRecords: MarriageRecordsCsvFamilioExporter(),
            DeathRecords: DeathRecordsCsvFamilioExporter(), DivorceRecords: DivorceRecordsCsvFamilioExporter()}


def exporter_of(record_set: object) -> FamilioCsvExporter | None:
    """The familio exporter of `record_set`; None for a kind that writes no familio CSV."""
    return _familio_exporters().get(type(record_set))


def tables(record_sets: Iterable[object], *, parish: str | None = None, years: Collection[int] | None = None,
           reviewed_only: bool = False) -> list[CsvTable]:
    """The familio CSV of each record set, in their order, nothing written: a set of a kind that writes none
    (a roll, a name list, the cards) is passed over, a set bound twice (an alias) is taken once. `parish`
    keeps the sets of that parish (the set's `village`), `years` the sets of those years; `reviewed_only`
    leaves the unreviewed records out (`verso.core.ratchet.unreviewed`)."""
    seen: set[int] = set()
    made: list[CsvTable] = []
    for record_set in record_sets:
        exporter = exporter_of(record_set)
        if exporter is None or id(record_set) in seen:
            continue
        seen.add(id(record_set))
        book: Any = record_set
        if parish is not None and book.village != parish:
            continue
        if years is not None and book.year not in years:
            continue
        records = [r for r in book.records if not unreviewed(r)] if reviewed_only else None
        made.append(exporter.table(book, records=records))
    return made


def merge_tables(tables: Iterable[CsvTable]) -> list[CsvTable]:
    """Tables of one name as one table — their rows one after another, in the order given — at the place of the
    first; tables of one name and different headers are refused."""
    merged: dict[str, CsvTable] = {}
    for table in tables:
        held = merged.get(table.name)
        if held is None:
            merged[table.name] = CsvTable(table.name, list(table.headers), list(table.rows))
        elif held.headers != table.headers:
            raise ValueError(f"{table.name}: two tables of one name and different headers")
        else:
            held.rows.extend(table.rows)
    return list(merged.values())
