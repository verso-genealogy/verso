# verso

[English](README.md) · **Русский**

verso — библиотека для генеалогических записей на русском языке, от Российской империи до советского
времени: метрических книг (рождения, браки, смерти), ревизских сказок, исповедных росписей и карточек
более поздних каталогов.
Корпус записывает каждую запись вызовом небольшого DSL на Python, по файлу на книгу и год; verso
читает эти файлы и строит из них профили Geni (в виде Terraform), справочники Familio, JSON записей,
CSV, хронологию и набор проверок, которые находят, в чём записи противоречат друг другу.

Библиотека — это два дистрибутива:

- **verso-core** — то, что не зависит от языка записей: рабочее пространство, реестр плагинов, загрузка
  записей в конвейер, кодек JSON записей, места и данные корпуса, храповик вычитки, HCL-модели Geni и
  команда `verso`.
- **verso-ru** — плагин для записей на русском: DSL (`verso.ru.dsl`), предметная область и имена,
  слой фактов, поиск дублей профилей, линтеры DSL, транслятор в Terraform для Geni, экспорт и импорт.

## Установка

На PyPI библиотеки пока нет: она ставится из git-тега (`<tag>` — один из [тегов](https://github.com/verso-genealogy/verso/tags)).

```sh
pip install "verso-core @ git+https://github.com/verso-genealogy/verso@<tag>#subdirectory=packages/verso-core"
pip install "verso-ru[xlsx,dsl-tools,sheets] @ git+https://github.com/verso-genealogy/verso@<tag>#subdirectory=packages/verso-ru"
```

Нужен Python 3.14+. Дополнения (extras): `xlsx` — справочник Familio (openpyxl); `dsl-tools` — переписывание
файлов DSL, `verso upgrade-dsl` (libcst); `sheets` — импорт из Google Sheets.

Корпуса в библиотеке нет, но есть базовый словарь имён (`[names] base = "ru"`: имена, отчества и их
старые написания). Корпус — это каталог с файлом `verso.toml`, где названы его сёла, его собственный
слой имён поверх базового и его данные: места, владельцы, события хронологии, статусы помещиков.
См. [рабочее пространство](docs/workspace.md) (на английском).

## Быстрый старт

В `examples/` лежит целое игрушечное рабочее пространство — одно выдуманное село, его слой имён поверх
базового, его места и помещик, четыре книги — и скрипт, который прогоняет библиотеку по его копии:

```sh
python examples/run.py --keep /tmp/toy     # затем загляните в /tmp/toy: CSV, records/, terraform/
```

См. [пример](examples/README.ru.md).

## Запись

```python
from verso.ru.dsl import Gender, Month, birth, birth_month, birth_records, person

births = birth_records(
    "ГА", "1", "2", "3", "Степанчиково", "Троицкая", 1850,
    *birth_month(Month.JANUARY,
                 birth(1, Gender.MALE, 3, 4,
                       child=person("Иванъ"),
                       father=person("Петръ", "Сидоровъ", "Ежевикинъ"),
                       mother=person("Анна", "Ѳомина"))),
)
```

В записи указан шифр книги (архив, фонд, опись, дело), село и церковь, а затем каждая статья так,
как её записал писарь, — имена в орфографии подлинника. То, что из записи следует (отчество и фамилия
ребёнка, фамилия матери, статус по умолчанию для книги), выводится; то, что в ней сказано, хранится
дословно. Дальше:

- `verso dsllint FILE…` — линтеры DSL (см. [справочник](docs/reference/linters.md));
- `verso export-csv --village V` — CSV на каждый набор записей, рядом с его файлом;
- `verso generate-tf --village V` — профили, союзы и документы Geni в виде Terraform;
- `verso export-records --village V` — JSON записей ([JSON записей](docs/records-json.md));
- `verso facts`, `verso date-order`, `verso reconcile`, … — проверки по записям
  ([все команды](docs/reference/commands.md)).

## Что публично

Корпусу, который пишет не автор библиотеки, она обещает то, на что такой корпус опирается:

- фасад DSL — `verso.ru.dsl` и три его каталога (`DSL_API`, [DSL](docs/dsl.md));
- статусы корпуса как `<каталог корпуса>.statuses`;
- схему JSON записей (`records-v1.json`) и её правило идентификаторов `r1`;
- команды `verso`, их флаги и коды выхода;
- ключи `verso.toml` и `village.toml`;
- коды линтеров и формат `dsllint --json`;
- строку списка храповика вычитки (`unreviewed_on_geni.tsv`).

Всё остальное — модули под фасадом, предметная область, транслятор — принадлежит самой библиотеке
и меняется без предупреждения. Пока версия 0.x, минорная версия может ломать совместимость: публичное
имя, которое уберут или переименуют, одну минорную версию живёт рядом с преемником и предупреждает
(`DeprecationWarning`), прежде чем уйти. См. [совместимость](docs/compatibility.md).

## Документация

Документация пока только на английском.

- Руководства: [рабочее пространство](docs/workspace.md) · [DSL](docs/dsl.md) · [плагины](docs/plugins.md) · [язык интерфейса](docs/i18n.md)
  · [JSON записей](docs/records-json.md) · [храповик вычитки](docs/review-ratchet.md)
  · [совместимость](docs/compatibility.md)
- Справочник, собранный из кода: [команды](docs/reference/commands.md) ·
  [ключи рабочего пространства](docs/reference/workspace-keys.md) · [линтеры](docs/reference/linters.md) ·
  [API DSL](docs/reference/dsl-api.md)
- [Как участвовать](CONTRIBUTING.md) · [Безопасность](SECURITY.md) · [Изменения](CHANGELOG.md)

## Лицензия

Apache-2.0 — см. [LICENSE](LICENSE) и [NOTICE](NOTICE).
