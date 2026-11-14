import os

from verso.ru.exporters.base import RecordsExporter, csv_writer


class BirthRecordsCsvExporter(RecordsExporter):
    def export(self, birth_records, target_dir=None):
        target_dir = os.getcwd() if target_dir is None else str(target_dir)
        return self._export_year(target_dir, birth_records, birth_records.year, birth_records.records)

    def _export_year(self, target_dir, birth_records, year, records):
        filename = os.path.join(target_dir, f"{birth_records.village}_{year}_births.csv")
        headers = [
            "№", "Страница", "Пол", "Рожд. День", "Рожд. Месяц", "Крещ. День", "Крещ. Месяц",
            "Имя реб. (совр. орф.)", "Имя реб. (совр.)", "Отчество реб. (совр.)",
            "Отец: Н.П.", "Отец: Статус", "Отец: Фамилия",
            "Отец: Имя (совр. орф.)", "Отец: Отчество (совр. орф.)", "Отец: Имя (совр.)", "Отец: Отчество (совр.)",
            "Мать: Статус", "Мать: Фамилия", "Мать: Имя (совр.)", "Мать: Отчество (совр.)",
            "Восприемник 1: Статус", "Восприемник 1: Н.П.",
            "Восприемник 1: ФИО (совр. орф.)", "Восприемник 1: ФИО (совр.)",
            "Восприемник 2: Статус", "Восприемник 2: Н.П.",
            "Восприемник 2: ФИО (совр. орф.)", "Восприемник 2: ФИО (совр.)",
            "Священник: ФИО (ориг.)", "Дьякон: ФИО (ориг.)", "Дьячок: ФИО (ориг.)", "Пономарь: ФИО (ориг.)",
            "Родственники", "Комментарий", "Имена в оригинале"
        ]

        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv_writer(f)
            writer.writerow(headers)
            for r in records:
                orig_names = []
                if r.child: orig_names.append(r.child.name_orig)
                if r.father:
                    orig_names.append(f"{r.father.name_orig} {r.father.patr_orig}".strip())
                if r.mother:
                    orig_names.append(f"{r.mother.name_orig} {r.mother.patr_orig}".strip())
                if r.god_parent1:
                    g1_patr = r.god_parent1.patr_orig if r.god_parent1.patr_orig else ""
                    orig_names.append(f"{r.god_parent1.name_orig} {g1_patr}".strip())
                if r.god_parent2:
                    g2_patr = r.god_parent2.patr_orig if r.god_parent2.patr_orig else ""
                    orig_names.append(f"{r.god_parent2.name_orig} {g2_patr}".strip())
                for rel in r.relatives:
                    rel_patr = rel.person.patr_orig if rel.person.patr_orig else ""
                    orig_names.append(f"{rel.person.name_orig} {rel_patr}".strip())
                orig_names_str = "; ".join(filter(None, orig_names))

                # Logic for comments
                comments = []
                if r.comment:
                    comments.append(r.comment)
                # Add comment from each person
                for person in [r.child, r.father, r.mother, r.god_parent1, r.god_parent2,
                               r.priest, r.deacon, r.dyachok, r.sexton]:
                    if person and person.comment:
                        comments.append(person.comment)
                for rel in r.relatives:
                    if rel.person.comment:
                        comments.append(rel.person.comment)
                final_comment = "; ".join(comments)

                # Build relatives string
                relatives_parts = []
                for rel in r.relatives:
                    name = f"{rel.person.name_orig} {rel.person.patr_orig}".strip() if rel.person.patr_orig else rel.person.name_orig
                    if rel.relationship_ref:
                        relatives_parts.append(f"{rel.relationship} {rel.relationship_ref}: {name}")
                    else:
                        relatives_parts.append(f"{rel.relationship}: {name}")
                relatives_str = "; ".join(relatives_parts)

                row = [
                    r.record_num,
                    r.page if r.page else "",
                    r.gender,
                    r.b_day,
                    r.b_month,
                    r.k_day,
                    r.k_month,
                    r.child.name_modern,
                    r.child.get_canonical_name(),
                    r.derive_child_patronymic(),
                    r.father.residence if r.father else "",
                    r.father.status if r.father else "",
                    r.father.last_name if r.father else "",
                    r.father.name_modern if r.father else "",
                    r.father.patr_old if r.father else "",
                    r.father.get_canonical_name() if r.father else "",
                    r.father.patr_modern if r.father else "",
                    r.mother.status if r.mother else "",
                    r.mother.last_name if r.mother else "",
                    r.mother.name_modern if r.mother else "",
                    r.mother.patr_old if r.mother else "",
                    r.god_parent1.status if r.god_parent1 else "",
                    r.god_parent1.residence if r.god_parent1 else "",
                    f"{r.god_parent1.name_modern} {r.god_parent1.patr_old if r.god_parent1.patr_old else ''}".strip() if r.god_parent1 else "",
                    r.god_parent1.get_fio() if r.god_parent1 else "",
                    r.god_parent2.status if r.god_parent2 else "",
                    r.god_parent2.residence if r.god_parent2 else "",
                    f"{r.god_parent2.name_modern} {r.god_parent2.patr_old if r.god_parent2.patr_old else ''}".strip() if r.god_parent2 else "",
                    r.god_parent2.get_fio() if r.god_parent2 else "",
                    f"{r.priest.name_orig} {r.priest.patr_orig}".strip() if r.priest else "",
                    f"{r.deacon.name_orig} {r.deacon.patr_orig}".strip() if r.deacon else "",
                    f"{r.dyachok.name_orig} {r.dyachok.patr_orig}".strip() if r.dyachok else "",
                    f"{r.sexton.name_orig} {r.sexton.patr_orig}".strip() if r.sexton else "",
                    relatives_str,
                    final_comment,
                    orig_names_str
                ]
                writer.writerow(row)
        print(f"Generated {filename}")
        return filename


class MarriageRecordsCsvExporter(RecordsExporter):
    def export(self, marriage_records, target_dir=None):
        target_dir = os.getcwd() if target_dir is None else str(target_dir)
        filename = os.path.join(target_dir, f"{marriage_records.village}_{marriage_records.year}_marriages.csv")
        headers = [
            "№", "Страница", "День", "Месяц",
            "Жених: Н.П.", "Жених: Статус", "Жених: Фамилия",
            "Жених: Имя (ориг.)", "Жених: Отчество (ориг.)",
            "Жених: Имя (совр. орф.)", "Жених: Отчество (совр. орф.)",
            "Жених: Имя (совр.)", "Жених: Отчество (совр.)",
            "Жених: Номер брака",
            "Невеста: Н.П.", "Невеста: Статус", "Невеста: Фамилия",
            "Невеста: Имя (ориг.)", "Невеста: Отчество (ориг.)",
            "Невеста: Имя (совр. орф.)", "Невеста: Отчество (совр. орф.)",
            "Невеста: Имя (совр.)", "Невеста: Отчество (совр.)",
            "Невеста: Номер брака",
            "Поручитель 1: Статус", "Поручитель 1: Н.П.", "Поручитель 1: ФИО (ориг.)",
            "Поручитель 1: ФИО (совр. орф.)", "Поручитель 1: ФИО (совр.)",
            "Поручитель 2: Статус", "Поручитель 2: Н.П.", "Поручитель 2: ФИО (ориг.)",
            "Поручитель 2: ФИО (совр. орф.)", "Поручитель 2: ФИО (совр.)",
            "Священник: ФИО (ориг.)", "Дьякон: ФИО (ориг.)", "Дьячок: ФИО (ориг.)", "Пономарь: ФИО (ориг.)",
            "Комментарий", "Имена в оригинале"
        ]

        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv_writer(f)
            writer.writerow(headers)
            for r in marriage_records.records:
                orig_names = []
                if r.groom:
                    orig_names.append(
                        f"{r.groom.name_orig} {r.groom.patr_orig}".strip() if r.groom.patr_orig else r.groom.name_orig)
                if r.bride:
                    orig_names.append(
                        f"{r.bride.name_orig} {r.bride.patr_orig}".strip() if r.bride.patr_orig else r.bride.name_orig)
                if r.witness1:
                    orig_names.append(
                        f"{r.witness1.name_orig} {r.witness1.patr_orig}".strip() if r.witness1.patr_orig else r.witness1.name_orig)
                if r.witness2:
                    orig_names.append(
                        f"{r.witness2.name_orig} {r.witness2.patr_orig}".strip() if r.witness2.patr_orig else r.witness2.name_orig)
                orig_names_str = "; ".join(filter(None, orig_names))

                comments = []
                if r.comment:
                    comments.append(r.comment)
                for p in [r.priest, r.deacon, r.dyachok, r.sexton]:
                    if p and p.comment:
                        comments.append(p.comment)
                final_comment = "; ".join(comments)

                row = [
                    r.record_num,
                    r.page if r.page else "",
                    r.w_day,
                    r.w_month,
                    r.groom.residence if r.groom else "",
                    r.groom.status if r.groom else "",
                    "",  # Groom surname (empty for now)
                    r.groom.name_orig if r.groom else "",
                    r.groom.patr_orig if r.groom else "",
                    r.groom.name_modern if r.groom else "",
                    r.groom.patr_old if r.groom else "",
                    r.groom.name_modern if r.groom else "",
                    r.groom.patr_modern if r.groom else "",
                    r.groom_marriage_num if r.groom_marriage_num else "",
                    r.bride.residence if r.bride else "",
                    r.bride.status if r.bride else "",
                    "",  # Bride surname (empty for now)
                    r.bride.name_orig if r.bride else "",
                    r.bride.patr_orig if r.bride else "",
                    r.bride.name_modern if r.bride else "",
                    r.bride.patr_old if r.bride else "",
                    r.bride.name_modern if r.bride else "",
                    r.bride.patr_modern if r.bride else "",
                    r.bride_marriage_num if r.bride_marriage_num else "",
                    r.witness1.status if r.witness1 else "",
                    r.witness1.residence if r.witness1 else "",
                    f"{r.witness1.name_orig} {r.witness1.patr_orig if r.witness1.patr_orig else ''}".strip() if r.witness1 else "",
                    f"{r.witness1.name_modern} {r.witness1.patr_old if r.witness1.patr_old else ''}".strip() if r.witness1 else "",
                    r.witness1.get_fio() if r.witness1 else "",
                    r.witness2.status if r.witness2 else "",
                    r.witness2.residence if r.witness2 else "",
                    f"{r.witness2.name_orig} {r.witness2.patr_orig if r.witness2.patr_orig else ''}".strip() if r.witness2 else "",
                    f"{r.witness2.name_modern} {r.witness2.patr_old if r.witness2.patr_old else ''}".strip() if r.witness2 else "",
                    r.witness2.get_fio() if r.witness2 else "",
                    f"{r.priest.name_orig} {r.priest.patr_orig}".strip() if r.priest else "",
                    f"{r.deacon.name_orig} {r.deacon.patr_orig}".strip() if r.deacon else "",
                    f"{r.dyachok.name_orig} {r.dyachok.patr_orig}".strip() if r.dyachok else "",
                    f"{r.sexton.name_orig} {r.sexton.patr_orig}".strip() if r.sexton else "",
                    final_comment,
                    orig_names_str
                ]
                writer.writerow(row)
        print(f"Generated {filename}")
        return filename


class CensusRecordsCsvExporter(RecordsExporter):
    """CSV for any household-list source — a ревизская сказка or an
    исповедная роспись (`CONFESSION_LIST`).

    The household number leads the row after the лист, because that is how a
    household is cited: «двор 94» on an ИР, «семья 3» on a revision tale. The
    column header follows `records.household_label`, so one exporter serves
    both without a flag.
    """

    def export(self, census_records, target_dir=None):
        import os
        target_dir = os.getcwd() if target_dir is None else str(target_dir)
        # Include the archive_suffix when present so multiple дела in the
        # same census year (e.g. several дела of подворные карточки of one year)
        # write distinct CSVs instead of clobbering one file.
        suffix = getattr(census_records, "archive_suffix", None)
        suffix_part = f"_{suffix}" if suffix else ""
        filename = os.path.join(
            target_dir,
            f"{census_records.village}_{census_records.year}_census{suffix_part}.csv",
        )
        unit_label = census_records.household_label
        headers = [
            "Лист", unit_label.capitalize(), "Фамилия", "Имя", "Отчество",
            "Роль", "Роль №", "Возраст", "Сем. положение", "Занятие",
            "Происхождение", "Примечание"
        ]

        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv_writer(f)
            writer.writerow(headers)
            # Mirror the translator's display-id rule exactly (see
            # `add_census_records`): an explicit `family_id` is used verbatim
            # and does NOT consume a numeric slot, so the CSV cites the same
            # household number as the generated document does.
            numeric_index = 0
            for h in census_records.households:
                if h.family_id:
                    display_id = h.family_id
                else:
                    numeric_index += 1
                    display_id = str(numeric_index)
                for m in h.members:
                    p = m.person
                    row = [
                        h.page,
                        display_id,
                        p.last_name_modern if p.last_name_modern else "",
                        p.get_canonical_name() if p.get_canonical_name() else (p.name_modern if p.name_modern else ""),
                        p.patr_modern if p.patr_modern else "",
                        m.role,
                        m.ref_member if m.ref_member is not None else "",
                        m.age,
                        m.marital_status if m.marital_status else "",
                        m.occupation if m.occupation else "",
                        m.origin if m.origin else "",
                        m.comment if m.comment else "",
                    ]
                    writer.writerow(row)
        print(f"Generated {filename}")
        return filename


class DeathRecordsCsvExporter(RecordsExporter):
    def export(self, death_records, target_dir=None):
        target_dir = os.getcwd() if target_dir is None else str(target_dir)
        return self._export_year(target_dir, death_records, death_records.year, death_records.records)

    def _export_year(self, target_dir, death_records, year, records):
        filename = os.path.join(target_dir, f"{death_records.village}_{year}_deaths.csv")
        headers = [
            "№", "Страница", "Пол", "Смерть День", "Смерть Месяц", "Погр. День", "Погр. Месяц",
            "Умерший: Н.П.", "Умерший: Статус", "Умерший: Фамилия",
            "Умерший: Имя (ориг.)", "Умерший: Отчество (ориг.)",
            "Умерший: Имя (совр. орф.)", "Умерший: Отчество (совр. орф.)",
            "Умерший: Имя (совр.)", "Умерший: Отчество (совр.)",
            "Умерший: Возраст",
            "Родственник: Родство", "Родственник: Н.П.", "Родственник: Статус",
            "Родственник: Имя (ориг.)", "Родственник: Отчество (ориг.)",
            "Родственник: Имя (совр. орф.)", "Родственник: Отчество (совр. орф.)",
            "Родственник: Имя (совр.)", "Родственник: Отчество (совр.)",
            "Свидетель 1: Статус", "Свидетель 1: Н.П.", "Свидетель 1: ФИО (ориг.)",
            "Свидетель 1: ФИО (совр. орф.)", "Свидетель 1: ФИО (совр.)",
            "Свидетель 2: Статус", "Свидетель 2: Н.П.", "Свидетель 2: ФИО (ориг.)",
            "Свидетель 2: ФИО (совр. орф.)", "Свидетель 2: ФИО (совр.)",
            "Священник: ФИО (ориг.)", "Дьякон: ФИО (ориг.)", "Дьячок: ФИО (ориг.)", "Пономарь: ФИО (ориг.)",
            "Комментарий", "Имена в оригинале"
        ]

        with open(filename, 'w', encoding='utf-8', newline='') as f:
            writer = csv_writer(f)
            writer.writerow(headers)
            for r in records:
                # Build orig_names_str
                orig_names = []
                if r.deceased:
                    orig_names.append(
                        f"{r.deceased.name_orig} {r.deceased.patr_orig}".strip()
                        if r.deceased.patr_orig else r.deceased.name_orig
                    )
                if r.relative:
                    orig_names.append(
                        f"{r.relative.name_orig} {r.relative.patr_orig}".strip()
                        if r.relative.patr_orig else r.relative.name_orig
                    )
                if r.witness1:
                    orig_names.append(
                        f"{r.witness1.name_orig} {r.witness1.patr_orig}".strip()
                        if r.witness1.patr_orig else r.witness1.name_orig
                    )
                if r.witness2:
                    orig_names.append(
                        f"{r.witness2.name_orig} {r.witness2.patr_orig}".strip()
                        if r.witness2.patr_orig else r.witness2.name_orig
                    )
                orig_names_str = "; ".join(filter(None, orig_names))

                # Build comment with auto-comment logic
                comments = []
                if r.d_day == r.b_day and r.d_month == r.b_month:
                    comments.append("Дата погребения не указана, взята дата смерти")
                if r.comment:
                    comments.append(r.comment)
                for p in [r.priest, r.deacon, r.dyachok, r.sexton]:
                    if p and p.comment:
                        comments.append(p.comment)
                final_comment = ". ".join(comments)

                row = [
                    r.record_num,
                    r.page if r.page else "",
                    r.gender,
                    r.d_day,
                    r.d_month,
                    r.b_day,
                    r.b_month,
                    r.deceased.residence if r.deceased else "",
                    r.deceased.status if r.deceased else "",
                    "",  # Deceased surname (empty)
                    r.deceased.name_orig if r.deceased else "",
                    r.deceased.patr_orig if r.deceased else "",
                    r.deceased.name_modern if r.deceased else "",
                    r.deceased.patr_old if r.deceased else "",
                    r.deceased.name_modern if r.deceased else "",
                    r.deceased.patr_modern if r.deceased else "",
                    r.age if r.age is not None else "",
                    r.relationship if r.relationship else "",
                    r.relative.residence if r.relative else "",
                    r.relative.status if r.relative else "",
                    r.relative.name_orig if r.relative else "",
                    r.relative.patr_orig if r.relative else "",
                    r.relative.name_modern if r.relative else "",
                    r.relative.patr_old if r.relative else "",
                    r.relative.name_modern if r.relative else "",
                    r.relative.patr_modern if r.relative else "",
                    r.witness1.status if r.witness1 else "",
                    r.witness1.residence if r.witness1 else "",
                    f"{r.witness1.name_orig} {r.witness1.patr_orig if r.witness1.patr_orig else ''}".strip() if r.witness1 else "",
                    f"{r.witness1.name_modern} {r.witness1.patr_old if r.witness1.patr_old else ''}".strip() if r.witness1 else "",
                    r.witness1.get_fio() if r.witness1 else "",
                    r.witness2.status if r.witness2 else "",
                    r.witness2.residence if r.witness2 else "",
                    f"{r.witness2.name_orig} {r.witness2.patr_orig if r.witness2.patr_orig else ''}".strip() if r.witness2 else "",
                    f"{r.witness2.name_modern} {r.witness2.patr_old if r.witness2.patr_old else ''}".strip() if r.witness2 else "",
                    r.witness2.get_fio() if r.witness2 else "",
                    f"{r.priest.name_orig} {r.priest.patr_orig}".strip() if r.priest else "",
                    f"{r.deacon.name_orig} {r.deacon.patr_orig}".strip() if r.deacon else "",
                    f"{r.dyachok.name_orig} {r.dyachok.patr_orig}".strip() if r.dyachok else "",
                    f"{r.sexton.name_orig} {r.sexton.patr_orig}".strip() if r.sexton else "",
                    final_comment,
                    orig_names_str
                ]
                writer.writerow(row)
        print(f"Generated {filename}")
        return filename
