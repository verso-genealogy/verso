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
  слой фактов, проверки консолидации (слияния дублей профилей), линтеры DSL, транслятор в Terraform для Geni, экспорт и импорт.

## Установка

С PyPI, начиная с 0.1.39:

```sh
pip install "verso-ru[xlsx,dsl-tools,sheets]"
```

`verso-ru` ставит `verso-core` своей же версии. Версия до 0.1.39 ставится из своего git-тега (`<tag>` — один из
[тегов](https://github.com/verso-genealogy/verso/tags)):

```sh
pip install "verso-core @ git+https://github.com/verso-genealogy/verso@<tag>#subdirectory=packages/verso-core"
pip install "verso-ru[xlsx,dsl-tools,sheets] @ git+https://github.com/verso-genealogy/verso@<tag>#subdirectory=packages/verso-ru"
```

Нужен Python 3.14+. Дополнения (extras): `xlsx` — справочник Familio (openpyxl); `dsl-tools` — переписывание
файлов DSL, `verso upgrade-dsl` (libcst); `sheets` — импорт из Google Sheets.

Корпуса в библиотеке нет, но есть базовый словарь имён (`[names] base = "ru"`: имена, отчества и их
старые написания). Корпус — это каталог с файлом `verso.toml`, где названы его сёла, его собственный
слой имён поверх базового и его данные: места, владельцы, события хронологии, статусы помещиков.
См. [рабочее пространство](docs/workspace.ru.md).

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
- `verso export-records --village V` — JSON записей ([JSON записей](docs/records-json.ru.md));
- `verso site --village V --out DIR` — записи статическим сайтом, книга за книгой ([сайт села](docs/site.ru.md));
- `verso facts`, `verso death-age`, `verso sibling-spacing`, … — проверки по записям
  ([проверки](docs/checks.ru.md), [все команды](docs/reference/commands.md)).

## Чтение сканов: плагин для Claude Code

Репозиторий — ещё и маркетплейс Claude Code `verso` с одним плагином, **verso-reading**: скиллы и агенты,
которые читают рукописные сканы — метрические книги, ревизские сказки и исповедные росписи, карточки
сельскохозяйственной переписи 1917 года — и записывают прочитанное в DSL.

```text
/plugin marketplace add verso-genealogy/verso
/plugin install verso-reading@verso
```

| Скилл | Для чего |
|---|---|
| `verso-reading:metric-books` | год метрической книги: цело ли дело, где начинаются части, читаемые кропы, чтение в два прохода |
| `verso-reading:census` | семья в ревизской сказке или исповедной росписи по возрастам, затем её дворы |
| `verso-reading:agri-census-1917` | подворные карточки 1917 года |
| `verso-reading:transcription` | путь через транскрипцию: `.txt` страницы для вычитки |
| `verso-reading:names` | словарь имён и замечания линтеров к именам |

Агенты плагина — `verso-reading:dsl-writer` (скан сразу в DSL) и `verso-reading:scan-reader` (чтение без
записи в DSL). Корпуса плагин не знает: где правила, региональные заметки и кадры, говорит AGENTS.md
проекта. Скиллы работают и в других агентах, через skills.sh. См. [плагин](plugins/verso-reading/README.md)
(на английском) — и [чего он стоит в контексте](plugins/verso-reading/README.md#what-it-costs).

Какая модель как читает такие сканы и сколько это стоит, измерено в
[статье](https://verso-genealogy.github.io/articles/models/) на [сайте статей](https://verso-genealogy.github.io/articles/).

## Что публично

Корпусу, который пишет не автор библиотеки, она обещает то, на что такой корпус опирается:

- фасад DSL — `verso.ru.dsl` и три его каталога (`DSL_API`, [DSL](docs/dsl.ru.md));
- статусы корпуса как `<the corpus directory>.statuses`;
- схему JSON записей (`records-v1.json`) и её правило идентификаторов `r1`;
- команды `verso`, их флаги и коды выхода;
- ключи `verso.toml` и `village.toml`;
- коды линтеров и формат `dsllint --json`;
- строку списка храповика вычитки (`unreviewed_on_geni.tsv`).

Всё остальное — модули под фасадом, предметная область, транслятор — принадлежит самой библиотеке
и меняется без предупреждения. Пока версия 0.x, минорная версия может ломать совместимость: публичное
имя, которое уберут или переименуют, одну минорную версию живёт рядом с преемником и предупреждает
(`DeprecationWarning`), прежде чем уйти. См. [совместимость](docs/compatibility.ru.md).

## Документация

- Руководства: [рабочее пространство](docs/workspace.ru.md) · [DSL](docs/dsl.ru.md) · [правила записи](docs/writing-records.ru.md) · [проверки](docs/checks.ru.md) · [плагины](docs/plugins.ru.md) · [язык интерфейса](docs/i18n.ru.md)
  · [JSON записей](docs/records-json.ru.md) · [сайт села](docs/site.ru.md) · [храповик вычитки](docs/review-ratchet.ru.md)
  · [совместимость](docs/compatibility.ru.md)
- Справочник, собранный из кода (на английском): [команды](docs/reference/commands.md) ·
  [ключи рабочего пространства](docs/reference/workspace-keys.md) · [линтеры](docs/reference/linters.md) ·
  [API DSL](docs/reference/dsl-api.md) · [проверки](docs/reference/checks.md)
- [Как участвовать](CONTRIBUTING.ru.md) · [Безопасность](SECURITY.ru.md) · [Изменения](CHANGELOG.md)

## Лицензия

Apache-2.0 — см. [LICENSE](LICENSE) и [NOTICE](NOTICE).
