# Инструменты сканов

[English](scans.md) · **Русский**

`verso scans` работает с кадрами отсканированной книги, уже лежащими на диске, — каталогом снимков альбома, какими их
дали читальный зал архива или телефон. Он проверяет, что альбом цел, находит, где начинаются части книги, режет
страницы на читаемые вырезки, выравнивает две страницы разворота строка в строку, увеличивает одну запись и находит,
где начинается каждая запись листа. Он ничего не скачивает и не пишет окон в `scans.toml`: доставить кадры на диск
(из фотобиблиотеки, из облачной папки) и запомнить окна — дело страницы вычитки (Verso).

## Установка

Инструментам нужен Pillow — extra `scans` пакета verso-core; кадрам HEIC с телефона нужен ещё pillow-heif — extra
`heic`. Без них чистые части (имена файлов, целостность, арифметика окон) по-прежнему импортируются и работают.

```bash
pip install 'verso-core[scans]'    # JPEG, PNG, TIFF
pip install 'verso-core[heic]'     # и HEIC
```

## Подкоманды

`verso scans --help` перечисляет их: сначала подкоманды ядра, потом каждого установленного плагина (`Plugin.scans`,
[плагины](plugins.ru.md)). `DIR` — каталог кадров. Любое окно задаётся в долях кадра или листа (0..1), а не в
пикселях: кадры одного дела гуляют в размере на несколько пикселей.

| Подкоманда | Пакет | Что пишет | Код выхода |
|---|---|---|---|
| `strips ALBUM --box X0,Y0,X1,Y1 --out DIR [--frames FIRST-LAST] [--per 20] [--size 900]` | core | `strips_<first>-<last>.jpg`, путь каждого печатается | 0; 2, если нет альбома или ни одного кадра |
| `quadrants IMAGE… --out DIR` | core | `<stem>_{tl,tr,bl,br}.png`, увеличенные втрое | 0 |
| `descreen IMAGE [l,t,r,b\|-] [SCALE] [MODE] [ROT]` | core | `<каталог IMAGE>/crops/<stem>_<box>_<scale>_<mode>_<rot>.png`, печатаются путь и размер | 0 |
| `jpeg DIR` | core | каждый HEIC каталога — JPEG того же имени, качество 92, поставлен прямо; HEIC удаляется | 1, если какой-то кадр не записан |
| `check DIR [--first N] [--last N]` | ru | отчёт: какие листы в альбоме, сторона пропущена или снята дважды, лист вне диапазона описи | 1 при любом изъяне |
| `headers DIR --out OUT [--strip 0.17] [--rows 8] [--frames]` | ru | `headers_NN.jpg`, контактные листы колонтитулов | 0 |
| `crops DIR --out OUT [--verso-only] [--part 1\|2\|3] [--from N] [--to N] [--with-count] [--x0] [--x1] [--scale] [--top 0.07] [--grey] [--enhance N] [--frames]` | ru | `<кадр:04d>_<лист>_{a,b}.jpg`, вырезки по полстраницы | 0 |
| `spread DIR --folio 120об [--band 0.07 0.56] [--scale 2.6] [--enhance N] [--out F]` | ru | `spread_<лист>_<y0>-<y1>.jpg` в DIR: полоса оборота над полосой лицевой стороны напротив | 1, если у альбома нет номеров листов или нет такой страницы |
| `zoom DIR --folio F [--part] [--col] [--row N OF] [--box X0 Y0 X1 Y1] [--scale 6] [--top 0.17] [--pad 0.02] [--colour] [--enhance N] [--frames] [--tag a] [--out F] [--layout F] [--village DIR] [--album-title T] [--angle DEG|auto]` | ru | `zoom_<лист>_<tag>.jpg` в DIR: одна запись, в сером и с автоконтрастом | 1, если нет такой страницы или окно не читается |
| `rows DIR --part N --folio F… [--x0] [--x1] [--count X0 X1] [--top] [--bottom] [--layout] [--village] [--album-title] [--out] [--angle DEG|auto] [--frames]` | ru | `rows_<first>[-<last>]_<part>.jpg` в DIR: метки и разрезы каждого листа; метки печатаются | 1, если лист задан неверно или нет такой страницы |
| `cards ALBUM OUT [--header B] [--table B] [--number B] [--leaf B] [--zoom IDX:x0:y0:x1:y1]` | ru | `NN.jpg`, `numbers.jpg`, `leaves.jpg` (или `zoom_NN.jpg`) карточек с/х переписи 1917 года | 1, если в ALBUM нет ни одного снимка |

Аргумент, который argparse не может прочитать, даёт код 2, как у любой команды `verso`.

Кадр альбомов verso-ru называется `<кадр>_<лист>.jpg` — `0118_57.jpg`, `0119_57об.jpg`, разворот
`0241(131об-132).jpg`, — и его страницы читаются по листам. Альбом, у которого остались имена телефона
(`IMG_0001.jpg`), читается по порядку кадров («кадр 12»), и это ничего не проверяет; `--frames` просит такую
нумерацию прямо.

## Что читается из `scans.toml`

Строфа альбома, `[album."<название>"]`, читается и никогда не пишется:

| Ключ | Что делает |
|---|---|
| `frames` | `"spread"`: кадр, названный по одному листу, держит и лист напротив — кадр, стоящий вертикально, остаётся одной страницей (`check`, `headers`, `crops`, `spread`, `zoom`, `rows`) |
| `top`, `bottom` | где начинается и кончается письмо, в долях листа (`zoom`, `rows`) |
| `rotate`, `rotate_frames` | поворот поверх собственной метки EXIF кадра — для альбома и для страницы |
| `enhance` | насколько усилить бледные чернила (`zoom`, когда `--enhance` не задан) |
| `village` | в собственной копии альбома — каталог, чей `scans.toml` долговечный: `enhance` спрашивается и там |

Все прочие ключи — окна (`[[album."…".box]]`), графы, остальные ключи вида, источник — пропускаются.
`check`, `headers`, `crops` и `spread` читают собственный `scans.toml` каталога альбома и его единственный альбом:
флага, который назвал бы другой файл или название, у них нет. `zoom` и `rows` читают тот, что назван `--layout`,
иначе собственный альбома, иначе `--village`; альбом — `--album-title` (точное название или единственный альбом,
чьё название его содержит), иначе единственный альбом файла. При `frames = "spread"` доли окна — доли листа, той
половины кадра, на которой он лежит, — во всех подкомандах; `--frames` читает кадры по порядку и оставляет их
целыми. `check` такого альбома ждёт стороны от первой до последней: лицевая перед левым листом первого разворота и
оборот после правого листа последнего — соседних альбомов. `scans.toml`, который не читается как TOML, подкоманды
отклоняют строкой и кодом 2.

Окна — дело страницы вычитки: их пишет Verso, а `verso-scans` (App) запоминает одно через
`zoom --record --remember` или все окна листа сразу через `windows`. `verso scans rows` находит метки и рисует их;
он ничего не пишет.

Лист, снятый наискось, берёт `--angle DEG|auto` (градусы против часовой стрелки, в пределах ±45; `auto` меряет
строки). `rows` поворачивает страницу ровно, прежде чем искать строки: лист, `--x0`/`--x1`, `--top`/`--bottom` и
`--count` меряются на странице как она лежит и переносятся на повёрнутую страницу вокруг своей середины, а линейка
рисуется на ней — её метки и разрезы в долях повёрнутой страницы. `zoom` переносит своё окно, названное на странице
как она лежит, на повёрнутую страницу и вырезает его ровно; строка, которую он пишет, называет поворот. Без
`--angle` ничего не поворачивается.

## В Python

`__all__` модулей публичен ([совместимость](compatibility.ru.md)):

| Модуль | Что даёт |
|---|---|
| `verso.core.scans.image` | `open_upright`, `turn_upright`, `cut_half`, `upright_size`, `turned_frame_size`, `image_names`, `heic_to_jpeg`, `convert_heic_frames`, `heic_clashes`, `pil`; `IMAGE_SUFFIXES`, `HEIC_SUFFIXES` |
| `verso.core.scans.window` | `Box`, окно в долях; `FULL_WIDTH` |
| `verso.core.scans.level` | `turn`, `turned_size`, `level_crop`, `line_angle`, `slant`, `carry`; `STRAIGHT`, `MAX_ANGLE` |
| `verso.core.scans.look` | `Look`, `legible`, `coloured_ink`; `PLAIN`, `INKS`, `MAX_ENHANCE` |
| `verso.core.scans.stanza` | `Stanza`, `StanzaError`, `for_album`, `rotation`, `enhance_for` |
| `verso.core.scans.sheets` | `contact_sheet`, `strips_sheet`, `fit_width` |
| `verso.ru.scans.folio` | `Page`, `parse_album`, `parse_frame`, `frame_pages`, `check_album`, `format_report`, `expand_spreads`, `renumber_scans`; `FRAME_PREFIX`, `VERSO_SUFFIX` |
| `verso.ru.scans.zoom` | `COLUMNS`, `DEFAULT_TOP`, `column_window`, `row_band`, `resolve` |
| `verso.ru.scans.rows` | `detect`, `count_window`, `ruler`, `sheet`, `parse_keys`, `pair`, `cuts_from` |
| `verso.ru.scans.album` | `load_pages`, `open_page`, `page_size`, `find`, `page_named`, `where`, `titled`, `note_frame_mode`, `album_of`, `spread_frames` |
| модуль подкоманды, `verso.core.scans.cli.<sub>`, `verso.ru.scans.cli.<sub>` | `HELP`, `add_arguments`, `run` (`Plugin.scans`); у `verso.ru.scans.cli.rows` ещё `leaf`, `report`; у `verso.ru.scans.cli.zoom` ещё `locate`, `cut`, `Target` — найденная страница, затем окно, вырезанное из неё, — вызывающий может отдать своё окно и поворот |
| `verso.ru.scans.cli` | `add_frames_flag`, `add_enhance_flag`, `add_angle_flag` |
| `verso.core.scans.cli` | `main` — сам `verso scans` |

Больше ничего в этих модулях не публично: значение типа, которого здесь нет (`Stanzas`, `Rows`), читают по его
атрибутам, а не импортируют.
