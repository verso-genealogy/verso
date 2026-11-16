---
name: agri-census-1917
description: >
  Read household cards of the 1917 All-Russian agricultural census («Всероссийская
  сельскохозяйственная и поземельная перепись 1917 г.», карточки для сплошной переписи
  сельских хозяйств) and write them into the DSL. Use when the user has a directory of such
  cards' frames — from an archive's reading room or wherever the project keeps them — and
  wants the households read, a surname found on them, or the cards turned into
  census_records().
---

A 1917 card is one household on one two-page form. It names **only the домохозяин**; every
other member is a relationship code and an age. So the card gives a household's shape — who
lives with whom, how old — and the names have to come from somewhere else (metric books,
ЗАГС). The work is therefore short per card but easy to get wrong in two ways: reading the
table in the wrong direction, and inventing names.

Downloading the cards from an archive's site (search by surname, stitching the viewer's tiles)
is the project's business: альбомы, архивы и региональные правила — в AGENTS.md проекта, with the
tools it has for each archive. This skill starts once the scans exist.

## 1. The cards' frames

The input is a directory of the cards' frames (`$FR` below); откуда кадры — в AGENTS.md проекта.
Cards downloaded from an archive's site often arrive named by the head of household
(`Манилов Иван Яковлевич. … уезд, … ф.1 оп.1 д.100.jpg`), so the directory carries no лист
numbers and `verso scans` reads it in frame mode. It needs `pip install 'verso-core[scans]'
verso-ru`.

A card is ~8800×6700 px. Read whole, it is downscaled to ~1.1 MP and nothing on it resolves.

## 2. Cut the three windows that matter

```bash
SC=/tmp/agri1917                    # scratchpad, never the project tree nor $FR
verso scans cards $FR $SC/cards
```

writes, per card, `NN.jpg` — the «Население» table over the card header — plus `numbers.jpg`
(the «№ карточки» box of every card, tiled) and `leaves.jpg` (the pencil лист number, top
right). Read `numbers.jpg` and `leaves.jpg` first: they give the card
order and the лист for `page=` in one image each. Then read the `NN.jpg` sheets. To check one
doubtful cell, `verso scans cards $FR $SC/cards --zoom IDX:x0:y0:x1:y1` enlarges one box of one card at 1400 px.

For a whole volost's cards (hundreds, not 28), find the households first with a strip of the
card's head line — «Фамилия, имя и отчество домохозяина» — over every card:

```bash
verso scans strips $FR --box X0,Y0,X1,Y1 --per 30 --size 1200 --out $SC/heads
```

A wide box stacks the lines one under another, each labelled with its frame; measure the box on
one card. Not yet run on a whole volost — check the first sheet before trusting the box.

The windows were measured on one дело of these cards. The printed form is the same everywhere,
but a different stitch may shift it — look at one card first and pass `--table/--header` if
the crop misses.

## 3. What the card says

**Header** (lower window): губерния, уезд, волость, селение, общество; «Фамилия, имя и
отчество домохозяина»; сословие («кр. бывш. помещ.»); национальность; «Приписной,
посторонний, беженец, гражд. пленный» (one is underlined); «Хозяйство отсутствующее —
«Отс.»»; «№ карточки» in a box on the right.

**Section I «Население (члены семьи и наличные наемные рабочие)»** (upper window). ⚠ The
table is printed ABOVE its own column header and fills **bottom-up**: the Х row is the one
just above the column numbers 1…21, the next member is one line higher. Read upward.

| гр. | мужчины | гр. | женщины |
|---|---|---|---|
| 1 | отношение к домохозяину | 12 | отношение к домохозяину |
| 2 | возраст | 13 | возраст |
| 3 | отметка о трудоспособности | 14 | то же |
| 4–6 | участие в с.-х. работах: в пахоте / в косьбе / в уборке полей | 15–17 | то же |
| 7–9 | промысел за последний год: название, положение, где занят | 18–20 | то же |
| 10 | отсутствующие более месяца («отс.») | 21 | то же |
| 11 | взятые по наборам и мобилизации («прз», «б. прз.» = был призван) | | |

**Relationship codes** (as written on the cards they were measured on): Х хозяин(ка) · Ж жена ·
С сын · Д дочь · О отец · М мать · Бр брат · Сн сноха · Вн внук/внучка (by the column it stands
in) · Пл племянник/-ца · Зя зять · Пра правнучка. «т.» on one card — тёща or тётка, not
resolved. An age of «0» is under a year.

**The head's own row**: a woman head writes «Х» in the WOMEN's column. A card filed in a
wife's name while the husband is at the front has «Х» in the men's column with no name —
the named woman is then the ЖЕНА, and the card says so only by that layout.

**Corrections on the card are evidence.** On one card the original head «Манилова Аграфена
Петровна» is struck through with «(умерла)» and «сынъ Ѳома Сидоровъ» written above — that is a
death between the listing and the check, and a mother–son link.

## 4. Write the DSL

One `census_records()` per дело, one `household()` per card, family_id = the card number,
`page=` = the pencil лист. If the project already has a 1917 card file, follow it.

```python
census = census_records(
    "АРХИВ", "1", "1", "100", "Маниловка", 1917,
    household("14",
              member(1, person("Аѳанасій", "Петровъ", "Маниловъ"), CensusRole.HEAD, age=34,
                     comment="гр. 10 «отс.», гр. 11 «прз» — призван, отсутствует"),
              member(2, person("?"), CensusRole.WIFE, age=33),
              member(3, person("?"), CensusRole.SON, age=9),
              member(6, person("?"), CensusRole.FATHER, age=58),
              page="27"),
    document_type="Всероссийская сельскохозяйственная и поземельная перепись",
    document_type_genitive="Всероссийской сельскохозяйственной и поземельной переписи",
    volost="Маниловская",
    household_label="хозяйство", household_number_label="№ карточки",
    reviewed=False,
    defaults=RecordDefaults(residence="Маниловка",
                            status_male="бывший помещичий крестьянин",
                            status_female="бывшая помещичья крестьянка"),
)
```

- **Unnamed members are `person("?")`.** Never fill a name from another source into the
  card's record — that belongs in consolidation, where it is a claim with its evidence.
- **Absent household** («Отс.»): the head alone, `age="?"`, with a comment. The census did
  not list the family; there is nothing to reconstruct.
- **Сноха** with one adult son in the house: `ref_member=<son>`; grandchildren then
  `parent_member=<son>`. With no son present (father at the front, or dead), leave her to
  the head — CPL003 will warn, and the warning is true: her husband is not on the card.
- **Brother's family** (Бр + Сн + small children): `ref_member=<brother>` on the сноха,
  `parent_member=<brother>` on the children, roles NEPHEW/NIECE as the code says.
- Mobilisation, absence, occupation go into `comment=` / `occupation=` verbatim-ish; they
  are how the card distinguishes a son at the front from a son who left.
- **PAF001 is expected here.** A 1917 card mixes «Кузьмичъ» and «Кузьминъ»; keep what is
  written. The linter exempts Soviet-era record sets only from 1918.

Then `verso dsllint <file>`, the CSV (`verso export-csv --village <village> --year 1917`), and the
project's staleness check of its generated files (the AGENTS.md проекта names it).

## 5. What to do with the result

The card is the best snapshot of a village between the last revision (1858) and the ЗАГС
books — but a snapshot of shapes. The genealogical payoff is in matching it:

- **Siblings among heads**: same patronymic + plausible ages. State it as an inference in the
  project's notes on the family, not in the DSL.
- **Forward to ЗАГС 1923–1926**: a son aged 10 in 1917 who registers a brother's birth in
  1925 «as brother» is the same person; an adult death with an age ≈ card age + 9 (ages
  drift by 2–4 years between sources).
- **Absent heads** («Отс.») are still heads of a двор that exists — they are the ones most
  likely to reappear in a later list.
