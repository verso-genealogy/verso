# DSL linter rules — what each check exists for

`packages/verso-ru/src/verso/ru/linters/checks/` holds the DSL linters; `packages/verso-ru/src/verso/ru/linters/dsllint.py` is the unified
wrapper that runs them all in one process with `--json` output (the repo-root `dsllint.py`
delegates to it, for IDE extensions).

The rules below are **not** derivable from the check source — they record why each one
fires and what the generator does downstream if you ignore it.

## A finding is its code, its params and its token

Every check answers through `verso.ru.linters.issue`: `issue(CODE, variant, line, level=…,
token=…, col=…, end_col=…, fix=…, **params)`, or `says(CODE, variant, token=…, **params)` spread
into a dict. Its text is the catalog's `CODE.variant` (`packages/verso-ru/src/verso/ru/locales/ru.toml`
and `en.toml`),
put together when it is read; the message is a `Text`, a `str` to every reader that compares
text, carrying `code`, `variant`, `params`, `token`.

- **params** hold what the DSL wrote (a name, a status, a place, a kwarg, a member's number), never
  a word of a language. A part said in words of its own («член двора 3 (Иван)», «умер») is a
  message itself (`t()`), and a role is named by its id and rendered from the catalog's forms
  (`status_words.role_word`/`who` → `forms.role.<id>.<case>`: `nom`, `gen`, `dat` and their
  capitals in Russian, `nom` alone in English). In `--json` a nested message is `{key, params}`.
- **token** is what the finding is about — the word a reader points at: VS Code and IntelliJ
  narrow the highlight by it (after `col`/`end_col` and `fix`, before the message's quotes), and
  Verso's offers answer a refusal by it. Give one wherever the finding is about a word of the line.
- **codes**: `linters/codes.py` — `LINTER_CODES`, every code each linter owns (`python -m tools.reference`
  documents them), and `PREFIX`, how the text opens (`[CPL002] `, `ESC001 `, none); a code-less
  finding is a defect (the baseline never holds one).
- **A new message**: its key in both catalogs — the Russian as the rule's author writes it, the
  English written anew, never a transliteration. `i18n.problems` (in the tests) refuses a key no
  code calls, a call no key answers, and a parameter one language lacks.
- **The Russian text is pinned byte for byte**: the samples under `tests/data/linter_samples/` and
  `tests/data/linter_messages_before.json` (`test_message_is_todays_text`) — the findings as they read before
  the catalogs. A deliberate rewording updates the snapshot in the same commit.
- **The baseline** (`baseline.py`, v2) keys a finding by file, code, params and occurrence, never
  its message.

## One tree a file, read-only

A check takes its tree from `checks/shared_ast.py`, never from `ast` itself: `shared_ast.parse(src)` for
`ast.parse`, `shared_ast.walk(node)` for `ast.walk`, `shared_ast.Visitor` for `ast.NodeVisitor` (whose `visit` it
does not override). The thirty-five registered checks then parse a file once and walk each node once between them,
where each parsed it and walked it again on its own — 35 parses a file, 24 million steps of `ast.walk` on one
village's files. The tree is every check's: **no check changes a node**, or the next check reads the change.

## `ages` — AGE001

Beyond malformed age literals, AGE001 flags an age that PARSES but spells a whole number
of years as a string — `age="1 год"`, `"5 лет"`, or a quoted bare number `age="70"` —
where the integer is meant. Not cosmetic: the generator appends `" лет"` to the death
doc's `Умерший:` line unless the age ends in a SUB-year unit (мес/нед/дн), so a whole-year
string doubles it — «… Мария Петровна 1 год лет». `split_age()` returns the same
(Лет, Мес, Нед, Дней) tuple for `1` and `"1 год"`, so the integer costs nothing.

Idioms (`"полгода"`, `"полтора года"` — they carry a MONTHS component), sub-year units and
compound ages are never flagged. Carries a `replace_kwarg` quick fix. NB the same
missing-year-unit branch still renders «полгода лет» — AGE001 cannot fix that, only the
generator can.

## `parent_status` — PSA001–PSA004

**Hard**: the corpus reached 0 findings, so a new one fails CI.

- **PSA001**: parent and child state DIFFERENT сословия — a ясачный child of a landlord's serf.
- **PSA002**: one of them omits `status=` and so inherits a different estate from
  `RecordDefaults`. Birth children and deceased children are exempt: `Birth`/`Death.__init__`
  derive their сословие from the parent via `statuses.child_status_for`, and bare `PEASANT`
  is compatible with qualified peasant estates.
- **PSA003**: newborn given an adult `..._MALE` instead of a `..._SON`.
- **PSA004** (hard from birth): husband and wife only — one states an estate,
  the other omits `status=` and the book's default names NONE («крестьянка» beside
  «крестьянин вотчины г-на Ноздрева»). Bare PEASANT under-specifies, which is harmless
  for a child (derived from the parent) and is why PSA001/PSA002 accept it; nothing
  derives a wife's estate, so on the default she loses it. First run: most of the findings sat in one
  village's early books (mothers, and a few deceased wives); a few more once «крестьянин
  отчины гг. Головлевых» became a catalog constant the rule could read (merged into
  GOLOVLEV_PEASANT). Fixed by `status_mother=` in the
  book's `DEFAULTS` — the wife written as her husband's: «жена крестьянина вотчины г-на
  Ноздрева» — and an explicit `status=` where one book holds a second wording (земской,
  the Горелово state peasants, the priest's wife «жена священника»).
  A временнообязанный and a крестьянин собственник (`TEMP_OBLIGED_PEASANT_MALE`,
  `PROPRIETOR_PEASANT_MALE`) read as plain PEASANT (`ESTATE_ALIASES`): a stage
  of land tenure after 1861, not an estate, so the wife on «законная жена крестьянина» is
  right. Without the alias the constant made many mothers of one village's 1870s books PSA004.
  `GOSUDARSTVENNYJ_PEASANT` reads as `STATE_PEASANT`: two names the catalog
  gives one estate, spelled alike; the wives and children (`STATE_PEASANT_LEGAL_WIFE`,
  `_WIFE`, `_SON`, `_DAUGHTER`) exist under the second only, and read by prefix a
  husband on the first and his wife on the second were PSA001.

**A finding is worded for the review page**: the person by role and name, both
statuses in their words, and the fix — the stated estate in the silent person's sex, as
words and constant, when the catalog holds it (`status_words.counterpart`): «[PSA004] У мужа
(Иванъ Петровъ) сословие не указано — по умолчанию книги он просто «крестьянин», а
умершая (Марія Сидорова) — «казенная крестьянка». У супругов одно сословие: укажите
мужу «казенный крестьянин» (KAZENNYJ_PEASANT_MALE).» Until then it said «у муж не указан
status=, и RecordDefaults даёт PEASANT_MALE — без сословия». What a status says, and how a
person is named, live in `checks/status_words.py`, shared with `residence_title`.

**The book's own words count as written** (`packages/verso-ru/src/verso/ru/linters/checks/file_bindings.py`):
`defaults=DEFAULTS` bound at the top of the file, and a status constant the file defines
itself (`GORELOVO_PEASANT = "…"`, read as its string; it shadows a catalog constant of
the same name, as it does when Python runs the file). Every Глуповы Горы file writes
both, and no other village; until it was fixed PSA ran there with no defaults and no
statuses at all, and hid two PSA002 (a priest's wife on «крестьянка»). VSR001, CSR001,
ULC, RTV and `single_line_calls` read `defaults=` through the same helper.

**«вотчины X» names owner X — in PSA only.** The Глуповы Горы books never write
«помещика»; `estate_of` reads only that, so PSA reads the surname closing «вотчины …»
(or the 1850s «отчины …») itself (the rest — г-на, гг., дворянина, малолетных детей, наследников — is honorific).
It is deliberately NOT in `estate_of`: estate-conflicts would then read the estate
changing hands (Тентетниковъ → Ноздревъ 1787, Ноздревъ → Головлевы 1821/22) as one person
holding two — Глуповы Горы had several, almost all of them that handover, which is
evidence of nothing.

Exempt estates skip a pair, but along two different axes. **Military** is exempt on both:
conscription pulled a man out of his father's estate, and our own constants say it did NOT
pull his wife out of it (`YASAK_SOLDIER_WIFE` → YASAK_PEASANT), so a soldier beside a
peasant wife is the model working. **Clergy** is exempt only between GENERATIONS — a rank is
not a fiscal estate and father and son routinely differ — but NOT between spouses: духовенство
was a closed estate whose wives belonged to it, and the books name them by the husband's rank
(«жена пономаря», «попадья», «дьячиха»), never «крестьянка». So the husband↔wife pairs (birth
father~mother, death муж~умершая) compare clergy while parent~child pairs skip it —
`SPOUSE_EXEMPT_ESTATES` drops `CLERGY_ESTATES` from `EXEMPT_ESTATES`. That split is what caught
a пономарь's wife who carried the parish «законная жена казенного
крестьянина» default. `ESTATE_ALIASES` folds POPADIA/DYACHIKHA/HIEREUS onto the rank each names,
so the wife's own word never reads as a rank of her own.

**Free text is read by its words**, with the `estate_of` that `estate-conflicts` uses, when
either side of a pair is a string no constant spells («дворовый человек помещицы Лукерьи
Кузьминичны Маниловой», «вдова мещанка», «однодворец»). It used to be skipped — and with it the
child the book's default made ясачный beside such a parent, which is exactly the error the
check exists for: the findings of its first run, every one a
statusless child or wife on the parish default. Two readings are deliberate:

- **A солдатка is compared by the origin her status names.** «солдатская жена из крестьян
  помещика X» kept X's estate (the reading `YASAK_SOLDIER_WIFE` → YASAK_PEASANT already
  encodes), so her child on the ясачный default is flagged; a bare «солдатка» names no estate
  and contradicts nobody. Military on the other side stays exempt.
- **An owner is matched by family, given name and the first four letters of the
  patronymic**: the books write «Демьяна Назаровича» and «Демьяна Назарова» Манилова for
  one man. Two owners of one family with different given names still differ, as their
  constants do. A bare «дворовый человек» names no owner and under-specifies any landlord.

**A landlord's дворовый and his крестьянин are one сословие**: the books
style one household either way — a man is «дворовый» in one book and «крестьянин» in another,
his wife and daughters «крестьянка», «крестьянская дочь» beside him. So
`estates_compatible` reads `X_DVOROVY` as `X_PEASANT`; the owner must still agree. That retired
5 PSA001 and made the constant path agree with the words, which `estate_of` already read that
way. Two PSA001 remain, both two owners of one family (a son of one owner's serf beside the
other's дворовый).

The words are coarser than the constants (ясачный ~ экономический are one `state`), which is
why constant↔constant pairs keep their own comparison: they are the only ones that can tell
those apart.

## `deaths_residence` — DRA001, DRA002

- **DRA001**: deceased and relative explicitly in DIFFERENT villages — one household, two residences.
- **DRA002**: a relative's `residence=` repeating the deceased's — the deceased keeps it in
  the DSL, the relative's copy is derived by `Death.__init__`.

## `deaths_relatives` — DRL001

A `death()` naming MORE than one relative. `add_death_records` emits `relatives[0]` ONLY;
the rest vanish with no profile, no union, no doc mention.

This is a guard on a latent limit, not a rule about the sources: no such record exists
today. Delete it together with the limit if the translator ever grows real multi-relative
support — the hard part there is making the 2nd parent `partner_2` of the SAME union, not
a second parent union.

## `deaths_burial_date` — DBD001, DBD002

- **DBD001**: the burial precedes the death.
- **DBD002**: a day its month does not have (31 November; 29 February outside a leap year).
  An impossible day is reported INSTEAD of DBD001, which it would always trip too: 31
  November is later than every November burial.

Asks at authoring time what `verso facts --check date-order` asks after generation. On its first run
that check found eight such records; six were fixed and two declared, and run
against the files as they stood before that this check reports all eight — seven DBD001,
one DBD002 — and nothing after. It gates at zero, not baselined.

Its first corpus run found four more that `date-order` could not: a burial one or two days
past its month's end, «29» February in a non-leap year and «31» June. Each falls AFTER its
death, so no ordering broke. All four read the same on the scan, so they are the book's own
and are declared, not changed.

Every one of the eight was a DSL shape, not a slip of arithmetic: a swapped day pair
(`death(1, M, 9, 8)`); a month override on the wrong side (`d_month=Month.SEPTEMBER` inside
an AUGUST block, so `b_month` inherits AUGUST); a next-month burial never stated
(`death(57, F, 31, 1)` in AUGUST — wants `b_month=Month.SEPTEMBER`); and the one DBD002, a
record under the wrong month block. So the check resolves months **the way
`death_month_year()` does**: the block fills `d_month`/`b_month` only where they are None,
an explicit `None` inherits, and an override on one side leaves the other on the block. A
month it cannot read as `Month.X`, or a `death_month(None, …)` block, orders nothing.

The comparison is `FactDate.definitely_before`'s: a burial with no day covers its whole
month; `b_day=0` is an empty column, not day nought. February is **Julian** before 1918,
where 1800 and 1900 are leap years; a record whose year cannot be read allows the 29th.

**The year boundary is flagged, deliberately.** A `death()` has ONE `year` for both dates —
there is no burial counterpart of `birth(k_year=)` — so death 31 December, burial 2
January cannot be stated: `b_month=Month.JANUARY` dates the burial eleven months BEFORE
the death, and that is what the CSV and the facts layer read. Staying silent would only
move the finding downstream. The message says to leave the out-of-year date undated and
state it in `comment=`; a December block never advises `b_month=Month.JANUARY`. A `b_year=`
kwarg is the real fix — build it with the first such record, of which the corpus has none.

`source_date_error="…"` on the record stands BOTH codes down: re-read on the scan, the book
itself buries first («померъ 9 | погребенъ 8»). An empty
string is no reason, as in `Death` and the facts layer.

## `marriage_residence` — MRA001

A party and their own parent with explicit DIFFERING villages — one household before the
wedding. Implicit sides are never compared; clergy-safe.

## `witness_side` / `witness_side_advisory` — WSD001–WSD006

Whom a wedding's поручитель stood surety for, declared on the person:
`witness3=person(…, side=Side.BRIDE)`. Часть 2 lists the sureties «по женихѣ» and «по
невѣстѣ». The slot (`witnessN`) is part of the res_name on Geni, so a side is NEVER
expressed by renumbering slots. A witness without `side=` is one whose side the record
does not say.

- **WSD001** (hard): `side=` anywhere but a marriage's `witness1..6` — a groom, a bride,
  the clergy, a relative, a godparent. Nothing reads it there.
- **WSD002** (hard): `side=` contradicts the same witness's `comment=` words.
- **WSD003**: the side is in words — a witness's `comment=` names it while `side=` is
  missing (declare it) or already says the same (drop the words: the Familio export
  writes them from `side=`), or the record's `comment=` names sides («поручители 1 и 2 —
  по женихе, 3 и 4 — по невесте») while a witness lacks `side=`. Reads «по жениху /
  женихе / женихѣ», «по невесте / невѣстѣ» and «со стороны жениха/невесты». A side named
  only in a `#` comment is out of reach: comments are not in the AST.
- **WSD004**: in one record some witnesses carry `side=` and some do not.
- **WSD005**: a groom's surety in a later slot than a bride's. The books write the groom's
  first, so look at the reading again — but never renumber an applied slot to fix it.
- **WSD006**: more than three sureties for one side; the Familio справочник has three
  columns per side.

Hard and advisory are two registry entries from one module, because the registry sets
severity per linter. The hard pair gated at zero from birth; the advisory four
go through the baseline ratchet.

## `civil_register` / `civil_register_advisory` — ZGS001–ZGS005

A book of the civil registry is `civil=True` on its record set: the same kinds and people as
a parish book, its second date a registration (`docs/dsl.md`). These ask what an act cannot
say, or what a book of 1918 on could not have written.

- **ZGS001** (hard): a church slot in a civil book — `god_parent1..4`, a marriage's
  `witness1..6`, the clergy (`priest=`, `deacon=`, `dyachok=`, `sexton=`), or a
  `christening()` entry. An act writes none of them; a parish book's template copied into the
  civil one is the usual cause. A death's `witness1/2` is not one: an act may name who
  declared it.
- **ZGS002** (hard): a civil birth registered before it was born, by an explicit `k_month=` or
  `k_year=`. A smaller registration day inside a `birth_month()` block is the next month, as
  `birth_month_year()` reads it, and is no finding.
- **ZGS003**: a book of 1918 on that names no church (`church=""`) without `civil=True`,
  whose registrations would read as christenings and burials. The year only guards it: a
  book of before with its church unknown is no finding (the corpus held none when the check
  came). Not the reverse — `civil=True` before 1917 is a civil registration too: the police
  books of the Old Believers (from 1874) and the sectarians (1879), the Kingdom of Poland's
  acts. The flag means «the second date is a registration», not «a Soviet book».
- **ZGS004**: an estate of the old order in a civil book — an owner, a ministry, an
  однодворец, дворянин, мещанин, купец — on a `status=` or the book's `RecordDefaults`.
  Estates were abolished in November 1917. Plain «крестьянин» is no finding: the acts kept
  it as a social position.
- **ZGS005**: a name in a civil book in the old orthography (ѣ, і, ѳ, ѵ, a final ъ), once a
  person. The DSL keeps the book's spelling; this asks whether the act or the typing hand
  wrote it so.

Hard and advisory are two registry entries from one module, as `witness_side`'s. Not
checked: a deed's births and deaths of one year in two files, one flagged and one not — a
check reads one file, and ZGS003 flags the unflagged one anyway. A death registered before it
happened stays DBD001's, worded «registration … precedes death» when the book is civil.

## `relative_attachment` — RLA001–RLA003

How a `relative()` attaches to the subject its `relationship_ref` names. Advisory: no
finding is a mechanical fix.

- **RLA001**: the ref does not attach — it names a slot the record lacks, or one the
  TRANSLATOR never resolves, so the relative is emitted with no relationship edge. Note this
  is deliberately stricter than `relationship_ref`, which only checks spelling against an
  allowlist. It found 44 sites, all since fixed: 41 unnumbered «восприемница» (rewritten to
  «восприемника №N»), and 3 that needed the translator to learn a ref it had never wired —
  «мать» (a relative of the mother, in незаконнорождённые births) and the new «поручитель №N»
  (a relative of a wedding поручитель, which a record had been spelling
  «восприемника №6» because marriages had no vocabulary for them).
- **RLA002**: the subject's patronymic cannot come from the father relative's name. Compares
  stems, not exact suffixes — Иона yields both «Ионична» (our rule) and the «Ионовна» the
  books write, and that is not a contradiction. `STEP_FATHER`/`FOSTER_FATHER` are never
  compared: a stepdaughter's patronymic legitimately names another man.
- **RLA003**: father and child surnames that cannot both be right (feminized for a daughter).

NOT checked, and deliberately so: **spouse** surnames. A HUSBAND/WIFE relative whose surname
does not feminize to their partner's looks like an error but is the norm — these books
routinely record a married woman under her MAIDEN surname (a widow named with her father's
surname beside her late husband; two sisters of one family in one birth, one of them married).
Both corpus findings of the RLA004 that briefly existed were that convention, so the
check was removed rather than baselined. Do not re-add it without a rule that separates a
maiden name from a wrong one.

When the SOURCE itself disagrees — a patronymic or surname that cannot come from the relative
the same entry names, verified against the scan — declare it on the record with
`marriage(..., source_kin_error="…")` and RLA002/RLA003 stand down, the way `source_date_error`
works for `date-conflicts`. The reason is free text and never reaches terraform. RLA001 is NOT
silenced by it: whether a ref resolves is our modelling, not the scribe's.

A surname missing on ONE side is silent in RLA003 — that is derivation territory
(`Death.__init__` already fills the deceased's from a FATHER/HUSBAND relative;
marriages and births do not yet), not a contradiction between two stated readings.

## `census_redundancy` — CRD001

Member surname/patronymic auto-derivable from the household head.

**A reference written in place is read**. `member(number, person, role,
ref_member, age, …)`, but `_Member` took `ref_member` from the fifth slot, `age`'s: a
positional reference named nobody (a SON fell back to the head, a GRANDSON or сноха to
no one), and an age written in place was taken for a member number. The tests had
followed the wrong order (`CensusRole.HEAD, 45` meaning age 45) and now write `age=`.
The corpus writes every reference as `ref_member=` (no `member()` of a corpus has a
fourth positional), so no finding moved. CSR001 and RTV share `_Member` and never read
its reference. `parent_member` (PM001/PM002) reads `ref_member`, `role` and `parent_member` as a
kwarg or in their places (`REF_MEMBER_AT` …, held to `member()`'s signature, 0.1.18).

## `status_redundancy` — VSR001

An explicit `status=` on a person in a BIRTH / MARRIAGE / DEATH record that repeats what
`defaults=RecordDefaults(...)` (in the call, or `defaults=DEFAULTS` bound at the top of
the file — Глуповы Горы had hidden ones) would apply anyway — removal
re-applies the identical
constant, so it is byte-neutral and auto-fixable. `census_status_redundancy` (CSR001) is
the same rule for `member()`; VSR001 is HARD where CSR001 is advisory, because the vital
corpus reached 0 in the commit that added the check.

Covers every slot `RecordDefaults.apply_to_*` actually visits: `groom`/`bride`,
`witness1…6`, `father`/`mother`, `god_parent1…4`, and each `relatives=` entry.
`status_groom`/`status_bride`/`status_mother` pre-empt the gendered default for their slot.

NOT covered — birth `child` and death `deceased`: `Birth.__init__`/`Death.__init__` derive
their сословие from the parent (`child_status_for`) BEFORE defaults run, so removing an
explicit status there yields the derived value, not the default.

**Nor the parent that derivation reads** (`checks/newborn_status.py`, shared
with `single_line_calls`). Only a WRITTEN parent status feeds it — the father's, else the
mother's; a death's first FATHER relative, else MOTHER — so when it is the one written
status the newborn's rests on, it is not redundant even though it equals the default:
without it the child takes the book's `status_male`/`status_female` («казенная
крестьянка») instead of the derived form («казенная крестьянская дочь»). Every repeated
status is weighed as removed together, because the IDE fixes and Verso's defaults dialog
take them all at once: of a father and a mother both on the default, the mother's is
flagged and the father's — the one consulted — stays. A status the AST cannot resolve is
kept. Found when «Умолчания книги…» could not add `status_mother` to one book's births:
the check demanded two mothers' `status=` go, and their going moved the children.
`single_line_calls` also stopped flagging a dead child's own status a parent's would
replace — the same derivation, seen from the child.

**The model is now conservative, deliberately**. Since that day the
translator also derives a child from a parent on the BOOK's default
(`RecordDefaults.apply_to_birth` / `apply_to_death` style the parents first), so a
written parent status equal to the default no longer moves the child when it goes —
it is in fact redundant. `newborn_status` still reads only written statuses and keeps it
as load-bearing: the error runs towards keeping a status, and no finding is new.
Teaching it the new rule would make VSR001 (hard) fire on those statuses across the
corpus, records on Geni and unreviewed among them, which the ratchet holds — a
cleanup of its own.

## `status_orthography` — SOR001

A `status=` (or its `RecordDefaults` forms) or `departure_reason=` written in pre-reform
orthography — ѣ, і, ѳ, ѵ, or a hard sign closing a word. A ruling of the maintainers: names (`person()`) and the source's own words in a member's `comment=` keep the
scribe's spelling; classification fields are modern, so they can be parsed and standardized,
as the status catalog already is. Reads a string literal
and a constant the file defines itself (through `file_bindings`); the message proposes the
modern spelling — `modern_spelling` also turns -аго into -ого and без- before a voiceless
consonant into бес- — and names the catalog constant when the spelling is one («священникъ»
→ PRIEST, «дьячекъ» → DYACHOK). **Hard from birth**: the first findings (Маниловка most of them,
«крестьянинъ собственникъ» among the commonest) were rewritten in the same
wave, so Verso refuses a save that writes a new one.

## `census_age` — CAI001–CAI003

- **CAI001**: lone `birth_day`/`birth_month` contradicting `age`.
- **CAI002**: `age` vs `previous_age` off the inter-revision gap.
- **CAI003**: `age=0` used as an "age not stated" sentinel. Read literally it dates the
  birth to the census year, so a head whose age the source omitted turns into a newborn and
  his children come out OLDER than him. Omit `age=` instead: a missing age means unknown
  and emits no birth event.

## `census_member_lines` — CML001

A `member()` that does not START its line — one person per row, as the revision list reads.
Unconditional: the first member after `household("12",` moves too. Does NOT require the
whole call on one line — kwargs may wrap. The existing ones were fixed by a one-off
reformatting script that re-parsed between edits and refused to write if the AST changed.

## `census_parent_link` — CPL001–CPL012

- **CPL001** (warning): внук/племянник with `ref_member`→non-head and no `parent_member` —
  the parent union is silently dropped though the ref looks like the father.
- **CPL002**: lineage member whose father is absent and unmodeled — consider a `hidden=True`
  intermediary.
- **CPL003**: сноха whose marriage can't be emitted — needs Rule A or a hidden husband.
- **CPL004**: married-in WIFE/сноха with a `parent_member` pointing at her husband, his
  ancestor or his sibling — an INVENTED parent union that surfaces as a Geni
  `duplicate_parents` conflict. Patronymic agreement is deliberately NOT treated as evidence.
- **CPL005**: `hidden=True` member that links to nobody — a fabricated leaf (a member
  invented to father a nephew and left dangling); the «добавлена вручную по другим
  материалам» comment is NOT evidence of attestation.
- **CPL006**: a RECORDED member whose `ref_member` points at a `hidden=True` one.
  `ref_member` states the relationship the SOURCE wrote down («дѣти ея», «жена его»), so it
  can only name somebody the source named; a hidden member is our reconstruction. Keep
  `ref_member` on the visible relative and put the reconstruction on `parent_member=`
  (two children written «дѣти ея»: `ref_member` at their mother, `parent_member` at the
  reconstructed father). Silent when the pointer runs the
  other way — a hidden member may reference anyone, that is the reconstruction's own
  wiring. The 12 households where the HEAD (or a second family's first member)
  ref'd a hidden FATHER were rewritten to `parent_member=` — the only generated
  change was three «merged unions» comment lines in `consolidated_unions.tf` (a mother-only
  union no longer minted and folded away) and the plan stayed empty. Zero findings now; the
  advisory ratchet fails CI on any new one.
- **CPL007**: a `role=None` member whose `ref_member` says nothing about what it ENCODES.
  With the role cleared, the same number is read as a spouse by one generator pass and as a
  parent by another (`generator.py` documents the convention it invented), so the meaning
  survives only in a prose comment. Settled by naming the number on a typed axis as well —
  `spouse_member=N`, `parent_member=N`, or `secondary_role` + `secondary_ref_member=N`. The
  first two are read by `verso.ru.facts.extract.census` and by nothing in the translator, so
  declaring one moves no generated byte; the third also MINTS the union. Thirteen in the
  corpus — twelve spouses and one father — all declared, so the check gates at zero.
- **CPL008**: `secondary_ref_member` naming the same member as `ref_member`. That axis is
  for an ADDITIONAL relationship the source's own role does not describe; aimed at the
  member `ref_member` already names it restates one, and restates it the expensive way —
  the translator mints a `geni_union` from it, duplicating the one the `ref_member` path
  already emits, and in some shapes the claim is incoherent (a SON whose secondary HUSBAND
  reference names his own father). 36 secondary references in the corpus, none of them
  equal, so this gates at zero too.
- **CPL009**: `ref_member` / `parent_member` / `secondary_ref_member` naming a member
  number that does not exist in the SAME household. All three resolve against that
  household's own numbering and nowhere else, so a number that misses resolves to nothing
  and the union is never emitted — with no error and no log. The other eight are blind to it
  by construction: each reads the reference's resolved TARGET, and a dangling number has
  none. Numbering is per household, so the shape comes from a household split, a
  renumbering, or a copy-paste from the household next door. The corpus case (a member with
  `parent_member=16` against a household of members 1–7) was written while the whole лист
  was still ONE flat `household()` with per-family restarting numbers — splitting it into
  several households stranded the link, and it sat as a no-op. A parent who genuinely lives in another
  household is linked with `father_ref=` (a consolidated profile name), never with a
  member number. **Zero findings corpus-wide — not baselined, so any new one fails CI.**
- **CPL010**: a member number used TWICE in one household. The number map every reference
  resolves through keeps the LAST member of a number (`CensusRecords` builds it as
  `{m.number: m}`), so the repeat silently replaces the earlier member: a reference reaches
  the later one, CPL001–CPL009 never see the earlier at all, and the facts layer — which
  keys an appearance on the number — collapses the two into one persona with two names.
  The one corpus case — a wife and her daughter of one двор both № 18 — was read off the
  scan (the roll numbers дворы, not people, so the member numbers are the
  transcriber's; the daughter is 19, the next member 20).
  **Zero findings corpus-wide — not baselined, so any new one fails CI.**
- **CPL011**: a hidden parent whose `ref_member` the translator turns into a
  spouse who cannot be one. The hidden-ancestor pass (`generator.py`) takes a hidden
  parent's `ref_member` as the second PARTNER of his children's union for every role but
  SON/DAUGHTER/STEPSON/STEPDAUGHTER — right for the corpus convention (a hidden FATHER at
  the MOTHER, an absent brother at his widow), wrong anywhere else. Fires when the pair is
  of one sex, or when a hidden BROTHER/SISTER/FATHER/MOTHER points at the head;
  `spouse_member=N` stands it down. One roll did it twice on one page — a hidden BROTHER with
  ref_member=1 made the head's brother the co-parent of a child, and another, given BROTHER
  with ref_member=1 on the review page, married the head's brother and, once the roll was
  folded, took three children into that brother's first marriage. No linter saw it; the
  plan did. Measured over a corpus's rolls: a few dozen hidden parents partnered this way, nearly all real
  marriages, the 26th the same shape (a hidden brother against the head — fixed, held, no
  generated byte). **Zero findings — any new one fails CI.**
- **CPL012**: a written patronymic that cannot come from the father the
  household links the member to — `parent_member=`, else a SON's or DAUGHTER's `ref_member=`
  (nothing else: a STEPSON's reference is his stepfather, a NEPHEW's an anchor, and a SON with
  no reference is the head's by default, which the rule does not read). Only a contradiction:
  the names agree by the keys `father-claims` compares with, moved for both to
  `verso.ru.naming.fathers` — the patronymic in the child's gender, the father's base form
  («Егоръ» ~ «Георгіевъ»), the stem of a name the table lacks — so the linter refuses nothing
  the facts layer accepts. A parent who is not a man (a widow's children, «дѣти ея») is
  skipped, and so is a member whose `patr_old` — the author's reading of a miswritten
  patronymic — agrees. CPL001 and CPL004 read a patronymic MATCH as weak evidence; this reads
  a MISMATCH, which is evidence. Measured on the corpus before it shipped: a handful of findings
  in a few dozen rolls. Three are wrong links (a ref_member at a 13-year-old brother instead of the father; a
  daughter whose patronymic is the head's, linked to his son; a «приемыш» entered as SON),
  three the names table reading «Нефед» as Мефодий against daughters written «Неофитова», and
  three the source's own (a foundling and a child born out of wedlock named by the godfather,
  a scribe giving a sister her brothers' patronymic) — each already said so in a comment. An
  advisory: the corpus baselines what it keeps.
- **A member numbered `-1`, `-2`… is read**. A negative number parses as
  `UnaryOp(USub, Constant)`, and `_int_literal` took only a `Constant`, so such a member
  and every `ref_member=`/`parent_member=` naming it were invisible to all eleven checks
  (and to PM001/PM002, CRD001's reference). One household of a roll married two hidden men
  to the head unseen (fixed by hand). The fix surfaced one more CPL011 in the next
  household, and nothing else across all the rolls measured.

## `residence_title` — RTV001, RTV002

A status names where its bearer lived; each rule belongs to ONE parish and runs only on
that parish's books — the record set's `village`, never the path.
The parishes, villages and owners are the corpus's data since 0.1.0 (`corpus/estates.toml`:
`[[state_peasants]]` for RTV001, `[[owners_and_state]]` for RTV002, `[village_aliases]`),
read through the workspace; a workspace without them runs neither rule.

- **RTV001** (hard) — the Горюхино parish (Горюхино, Собакевичево). A landlord's serf lives
  in that landlord's village (`[landlords]` of `corpus/estates.toml`, keyed on the landlord's
  initials; until 0.1.0 the code's `LANDLORD_VILLAGES`); the
  ясачные / казённые in Горюхино. **The ясачные half runs only in books of Горюхино or
  Собакевичево**: before that it ran everywhere and refused a Verso save in
  the Глуповы Горы books — «казенная крестьянка» деревни Горелово, which is right. The
  landlord half still runs everywhere: those owners occur in no other parish.
- **RTV002** (hard) — Глуповы Горы: the село was its owners' (Тентетниковъ → Ноздревъ 1787 →
  Головлевы 1822), Горелово a state village. An owner named in Горелово («вотчины»,
  «отчины», «помещика», «г-на», «гг.», a дворовый), or a state peasant (`estate_of` =
  `state`) in the село, is a contradiction. 0 in the corpus when it landed.
- **A bare «крестьянин» is allowed** — a peasant status naming no estate, in the село or
  in Горелово, written or the book's default. RTV003 (advisory, baselined, later retired) asked for the owner or the ведомство on every one before 1861 —
  hundreds in the baseline when it went — and refused a Verso save of the 1839 books, which write
  plain «крестьянин» and «законная жена крестьянина». A transcription keeps what the
  source says; RTV002 still checks that the estate a status DOES name fits the village.

RTV002 reads the status a person ENDS with — written, else the book's
`RecordDefaults` for the role and sex — because the default is where the error lives.
It skips soldiers («сторож казённого бора, рядовой солдат» lived where service put him),
a reconstructed roll member (`hidden=True`, not in the book), and a newborn or a dead
child with a parent in the record: the parent is what to fix. That skip is sound only
because such a child DOES get the parent's estate: until the same day the catalog held no
`GOLOVLEV_*`/`NOZDREV_*` child forms, and 77 children (1820s–1850s) of fathers styled
«вотчины гг. Головлевых» fell to the book's bare «крестьянин» unseen. A new owner wording
needs its `_SON`/`_DAUGHTER` beside it, or `child_status_for` derives nothing.

**The messages name the person** («Муж (Захаръ Петровъ) живёт в Горелово…»), as PSA's
do since the same day.

## `unmapped_location` — ULC001

Warning: residence / census member origin/destination not among the corpus's places
(`corpus/places.toml`, `verso.core.places`); the message says so in Russian since 0.1.0.

## `single_line_calls` — and the only auto-fix

Every `person(...)` on one line, plus "use the constant, not the string literal" and
"this kwarg repeats RecordDefaults". The multi-line half is the one DSL finding whose
repair contains no judgement at all — an editor wraps a dozen calls at once and the fix is
whitespace — so it is the one the linter can apply itself:

    python3 dsllint.py --fix [--dry-run] <files>      # or: verso dsllint --fix [--dry-run] <files>

`packages/verso-ru/src/verso/ru/linters/fixes.py` joins the wrapped lines, tightens the brackets and drops the magic
trailing comma, then **rewrites only if the file re-parses to an identical AST**. That is
the whole safety argument: whitespace inside a call carries no meaning, so an unchanged
tree means an unchanged record, and any join that would change one is discarded instead.
A call carrying a `#` comment is skipped and reported — joining would swallow the rest of
the line, and comments are not in the AST, so the comparison could not catch it.

The constant/redundant-kwarg halves keep their `replace_kwarg` / `remove_kwarg` fix dicts
for the IDE extensions; `--fix` deliberately does not apply those, because choosing a
constant is a judgement the extensions surface to a human. Verso's save does apply the
constant fix (`bookdefaults.replaceable`) — to the one record saved, where
the human typed the words and pressed «Сохранить» — and names the replacement in its
reply. That fix carries `kwarg` (the field), as the removal fixes do; the other
`replace_kwarg` fixes (AGE001, `genders`, `relationship_ref`) are never applied.

## `reviewed_redundancy` — RVR001

A `reviewed=` restating the value it would already inherit. Three levels resolve
innermost-first — the record → `page(…)` → its record set (`name_list_records`,
`census_records`, `birth_records`, `marriage_records`, `death_records`; default `True`) —
so an inner flag is redundant exactly when the value it would otherwise inherit is the
same, and deleting it is a true no-op. Both `True` and `False` are flagged: holding a лист
twice is as repeatable as releasing one twice.

**Every record type participates** since births, marriages and deaths
began defaulting to `None` like the rest (`packages/verso-ru/src/verso/ru/dsl/records/reviewed.py`) and their record
sets (`birth_records`, …) took a file-level `reviewed=`. Before that they defaulted to
`True`, `page(reviewed=…)` never reached them, and removing an explicit flag there would
silently have flipped `False` to `True` — so the check refused to look at them. Widening it
found nothing in the corpus. Removing a redundant flag never moves a ratchet line: the
fingerprint leaves `reviewed=` out (`packages/verso-core/src/verso/core/ratchet.py`).

Advisory despite the fix being mechanical, because of WHEN it fires: a лист is released by
adding `page(…, reviewed=True)` on top of entries already released one by one, so every
finding appears in the middle of a sweep, in a file someone is still editing. Gating would
fail CI on the very commit that closes a лист. Carries a `remove_kwarg` fix for the IDE
extensions; `--fix` does not apply it (see `single_line_calls` above for why that bar is
an identical-AST comparison, which a kwarg removal cannot meet — RVR001's guarantee is
semantic, not syntactic).

First run: a few findings, all in one file, removed in the same commit that added the
check. `verso generate-tf` produced a byte-identical tree afterwards, which is the
guarantee stated rather than assumed.

## `names_csv` — NCSV001–NCSV006, and it is not a DSL check

The one linter in this tree that reads **`names.csv` itself** rather than DSL
files, so it is not in the `dsllint` registry: `verso names-csv`, run from
`py-lint`. `checks/names` validates `person()` calls AGAINST the table; this
validates the table's own claims.

- **NCSV001** `Имя-основа` names a form the table does not hold as an `Имя` —
  `canonicalize_name` then returns a name that is not in the dictionary.
- **NCSV002** `Имя-основа` repeats `Имя`; a canonical row leaves it empty.
- **NCSV003** `Имя-основа` points at a name that is itself a variant.
- **NCSV004** the row repeats an earlier row in every column — dead weight,
  because `setdefault` already ignored it.
- **NCSV005** / **NCSV006** `Пол` outside `М`/`Ж`; empty `Имя`.

**NCSV003 is advisory, and that is the interesting part.** The chain is a real
defect — `canonicalize_name` does not follow one, so `Саламанида → Салманида →
Соломонида` stops a step short and two spellings of one woman get different
res_names. But flattening it CHANGES what `canonicalize_name` returns, and that
feeds `res_names`, so every applied village would need `moved` blocks. It is a
migration a human schedules, not something a linter may force. Eight chains
stand today.

**Row order is deliberately NOT checked, and the file must never be sorted.**
The table compiles into its layer (`verso.ru.naming.legacy`) index by index «first
row wins», so the first row carrying a key wins and the later ones are the variants it
deliberately shadows — «Абрамов» resolving to «Авраамович» rather than
«Абрамович» is the mechanism, not a duplicate. 572 of 4049 rows sit out of
alphabetical order; sorting them would silently re-pick 400+ canonical forms.
`verso.ru.cli.names add` exists so nobody has to place a row by hand under that
constraint: it follows the nearest smaller name, is pushed FORWARD past any row
whose index key it would steal, and splices one line rather than rewriting the
file (which would strip hand-written quoting from six unrelated rows).

## `dead_code` — DEAD001 and DEAD002, and neither is a DSL check

The second linter in this tree that reads **the source itself** rather than DSL
files, so like `names_csv` it is not in the `dsllint` registry: `verso dead-code`,
run from `py-lint`. It reports a function defined in the packages of `verso` — the library,
the App and the adapter, found by import (under `lib/` and `app/`) — whose name appears
nowhere in the repository — not in the code, not in the three trees of tests, not in `tools/`,
not in the per-village DSL or config.

**Why it exists.** The data side has had such checks for a year — CST001
(stale stubs), SMB001 (moved blocks that address nothing), ROV001 (dead
overrides), `stale_claims` — each hunting a config entry that no longer points
at anything. The Python side had none: ruff catches unused imports and locals,
and pyright's `reportUnusedFunction` is **off by decision**
(`pyrightconfig.json` says why — it counts same-file use only, so every
cross-module helper would false-positive). `_emit_clergy` sat in
`generator.py` with no call site for as long as anyone can remember, while
three tests pinned that clergy profiles are NOT emitted.

**Why it is name-based, and why that under-reports.** Every definition in
the packages of `verso` is collected; every name loaded, attribute accessed, string literal
written or symbol imported anywhere goes into one flat set. A definition whose
name is not in that set is reported. Two functions sharing a name therefore
shield each other, and a short name that is also an ordinary word (`at`,
`child`, `key`) is shielded by every unrelated use. That is the intended
trade: resolving each call to its definition would eventually report a live
function because an import was spelled unusually, and **a lint that deletes
live code once is never trusted again**. Missing rot is the cheap failure.

**Exemptions, and the reason for each.** `main` — every CLI is reached as
`python -m verso.ru.cli.X`, so no module names it. `visit_*` and `generic_visit` —
`ast.NodeVisitor` dispatches on the node class name at runtime. `__dunder__`.
A name called by a runtime string that this scan cannot see belongs in
`EXEMPT_NAMES` **with an explanation**, not silently.

**It gates at zero**, like VSR001 rather than like the advisory ratchet: the
seven findings of its first run (`_emit_clergy`, `full_name_en`,
`duplicate_title`, `_exact_span_years` and three unread alias properties in
`verso.ru.facts.model`) were removed in the commit that added the check, so a new
finding is a regression rather than debt.

### DEAD002 — a schema key the linter accepts and no code reads

`profiles_to_consolidate` entries are consumed key by key — `entry.get("keeper")`,
`cfg_entry.get("preference")` — so a key in `PROFILE_SCHEMA_KEYS` that appears
nowhere else is one the linter ACCEPTS and the generator ignores. That is worse
than dead code: the config looks like it says something, a curator writes it in
good faith, and nothing happens. `current_resource_name` had fourteen such
lines in Горюхино and `ignore_birth_dates_before` one; all fifteen were
removed with the check, and the tree regenerated byte-identical, which is the
proof they never did anything.

Two distinctions the first draft got wrong, both worth keeping:

* **The per-village `generate_config_names.py` files are code and DO count.**
  Нижняя Яичница's reads `union_data.get("union_names", [])` to build its own
  move list, so the first draft called a live key dead. Only the two schema
  set-literals are hidden from the scan now, not the whole module that
  declares them — `lint_config` itself uses keys elsewhere
  (`names_field = "profile_names" if ... else "union_names"`).
* **Writing a key is not reading it.** A string that is a KEY of a dict literal
  is the config stating something — the very data whose liveness is in
  question — so it does not count as a use. Counting it made every key alive by
  virtue of being written.

References from `tests/` do not count either: a test asserting the schema
accepts a key is not a consumer of it, and that was exactly the shape the two
legacy keys had.

⚠ Do not add `terraform` to `SKIP_PARTS`. The village `terraform/` trees hold
`.tf` and no Python, but `packages/verso-core/src/verso/core/targets/geni/` is a package — skipping the bare
name hid `generator.py` and `profile.py`, which is where two of the seven
findings were.

## `name_gender_agreement` — NGA001, NGA002 (advisory)

The surname (NGA001) or the patronymic (NGA002) of a `person()` in the other
gender's form: «Степанъ Васильевъ Ляпкина», «Ксения Антонова Сидоров». The
gender is the explicit `gender=`, else the first name's; a name that is unknown
or carries «?» is skipped, and so is a surname with no gendered ending.

`names` only checks that a name and a patronymic exist, and `genders` that a
name fits its role; nothing compared the parts of one name with each other.
That is how an entry slipped through: the scribe's «Степанида Васильева» was
corrected on review to «Степанъ Васильевъ» and the surname stayed feminine. On the
corpus at introduction it found two more.
Advisory, under the ratchet baseline.

## `dsl_imports` — IMP001

A DSL file imports the DSL's facade and nothing else (DSL v1): `verso.ru.dsl`, its
catalogs `verso.ru.dsl.statuses` / `.causes_of_death` / `.marital_status`, and the corpus's
own `corpus.statuses`. Any other import — `geni.*` (DSL v0, whose alias is gone), `calendar`
(`Month` comes from the facade, the same object), `os`, `__future__`, a module of the library
— is «импорт не из фасада DSL: <модуль>», and «— verso upgrade-dsl <файл>» after it for
`geni.*` and `calendar`, the imports the codemod rewrites (the rest it refuses, or keeps an
`os` the file uses). The facade is the DSL's contract (`verso dsl-surface`); a file reaching
past it ties itself to the library's insides, which move. **Hard from birth**: the codemod
left every file on the facade, so a new finding fails CI. No `--fix` — `verso upgrade-dsl` is
the fix for a v0 import, and it checks the ratchet's prints; any other is taken out by hand.

## Other checks

`names`, `genders`, `hidden_flag`, `parent_member`, `relationship_ref`,
`birth_redundancy`.

## `retractions` — RET001–RET003

An age retraction that names no age. `member(source_age_error=)` /
`member(previous_age_error=)` / `death(source_age_error=)` withdraw an age — the facts
layer stops believing it and the translator derives no birth from it — and
`death(namesake=)` says a burial age is right but belongs to a second child of that name.
On a record that states no such age each of them is a slip (the wrong line, the wrong
kwarg, a figure never transcribed):

- **RET001**: `previous_age_error=` with no `previous_age=` and no «прошлая РС:» marker.
- **RET002**: `source_age_error=` / `namesake=` on a record with no age (a roll line dated
  by a typed `birth_year=`/`birth_day=` counts as stating one).
- **RET003**: both retractions on one roll line — the whole-line one already covers it.

Hard from birth (0 findings on the whole corpus).
