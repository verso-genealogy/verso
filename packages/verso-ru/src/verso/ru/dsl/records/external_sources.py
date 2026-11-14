"""DSL records for *external biographical sources* — evidence of a person from a
published external catalog (not a parish metric book).

Two sub-kinds are modelled today:

* **судимость** — the pre-revolutionary criminal-record gazette
  «Ведомости справок о судимости 1870–1927», indexed on familio.org
  (`/catalogs/vss/persons/<uuid>`). The proof is the verbatim gazette entry.
* **военная служба** — WWI participant lists from gwar.mil.ru
  («Памяти героев Великой войны 1914–1918»). The proof is the hero card.

Each record *describes a person* and carries a `SourceCitation` (the provenance
of the claim). The translator mints a `geni_profile` from the person and a proof
`geni_document` linked to it; the freshly-minted profile is reconciled onto the
already-modelled person in a later, explicit consolidation pass — the same
lifecycle as every other record type. Records therefore hold **no** link string
to a pre-existing profile.
"""
from __future__ import annotations

from calendar import Month
from enum import Enum

from verso.ru.domain import EventDate, Person
from verso.ru.naming import get_gender_from_name
from verso.core.written import VERB_ATTR, captures_written


class ExternalSourceKind(Enum):
    """The catalog family a record comes from (the record_type in village.db)."""

    CRIMINAL = "судимость"
    WWI = "военная служба"
    WWII = "Великая Отечественная война"


class WwiDocumentType(Enum):
    """A gwar.mil.ru hero-card type («Тип документа»).

    Closed set — pick the member matching the card's «Тип документа»; the
    `.value` is the verbatim gwar label rendered into the proof document. The
    `kind` axis (`wwi_record` vs `criminal_record`) is what drives generation;
    `document_type` is a within-gwar sub-classification that does not change the
    emitted resources, but a closed enum keeps the 55-odd call sites typo-proof
    and lets ESC003 reject `casualty_reason` on award documents.
    """

    CASUALTY_LISTS = "Именные списки потерь"
    CASUALTY_CARD_LOWER = "Карточка на выбывших (нижние чины)"
    WOUNDED_NOTICE = "Уведомление о приеме раненого"
    ARRIVAL_CARD_HIGHER = "Карточка на прибывших (высшие чины)"
    ARRIVAL_CARD_LOWER = "Карточка на прибывших (нижние чины)"
    AWARD_LISTS = "Списки награжденных"
    REPORTING_CARD = "Отчетно-осведомительные карточки"
    POW_CARD = "Карточки военнопленных"

    @property
    def is_award(self) -> bool:
        """Award documents («Списки награжденных») record a decoration, not a
        casualty: `casualty_reason` («причина выбытия») is meaningless on them
        (enforced by ESC003)."""
        return self is WwiDocumentType.AWARD_LISTS


class WwiiDocumentType(Enum):
    """A pamyat-naroda.ru/podvignaroda.ru card type («Тип документа»).

    Closed set, mirroring `WwiDocumentType` — pick the member matching the
    card's «Тип документа»; the `.value` is the verbatim label rendered into
    the proof document. `.is_award` marks the three award-document members,
    where `casualty_reason` is meaningless (enforced by ESC003) and `award`/
    `award_number` are expected (enforced by ESC004)."""

    NAGRADNOY_LIST = "Наградной лист"
    AWARD_ORDER = "Приказ (указ) о награждении"
    ANNIVERSARY_AWARD = "Юбилейная картотека награждений"
    CASUALTY_REPORT = "Донесение о безвозвратных потерях"
    MEMORY_BOOK = "Книга памяти"
    SERVICE_CARD = "Учётно-послужная картотека"
    POW_CARD = "Картотека военнопленных"
    AWARD_CARD = "Картотека награждений"
    CASUALTY_CLARIFICATION = "Документ, уточняющий потери"
    WOUND_CARD = "Картотека ранений"
    TRANSIT_POINT = "Военно-пересыльные пункты и запасные полки"
    UNIT_ROSTER = "Именной список части"

    @property
    def is_award(self) -> bool:
        """Award documents (наградной лист / приказ о награждении / юбилейная
        картотека / картотека награждений) record a decoration, not a
        casualty — same rationale as `WwiDocumentType.is_award`."""
        return self in (
            WwiiDocumentType.NAGRADNOY_LIST,
            WwiiDocumentType.AWARD_ORDER,
            WwiiDocumentType.ANNIVERSARY_AWARD,
            WwiiDocumentType.AWARD_CARD,
        )


# Human-readable catalog names, used as the document title prefix.
_CATALOG = {
    ExternalSourceKind.CRIMINAL: "Ведомости справок о судимости 1870–1927",
    ExternalSourceKind.WWI: (
        "Списки участников Первой мировой войны "
        "(проект Памяти героев Великой войны 1914–1918)"
    ),
    ExternalSourceKind.WWII: "Память народа (проект Минобороны РФ)",
}

# Default Geni document labels per kind. WWI/WWII map to the attested
# "Military" label; судимость has no dedicated Geni label, so it falls back
# to "Other".
_DEFAULT_LABELS = {
    ExternalSourceKind.CRIMINAL: ["Other"],
    ExternalSourceKind.WWI: ["Military"],
    ExternalSourceKind.WWII: ["Military"],
}


class SourceCitation:
    """Provenance of an external-source claim — where the evidence lives."""

    def __init__(
        self,
        catalog: str,
        source_url: str,
        original_text: str | None = None,
        bibliography: str | None = None,
        archive: str | None = None,
        fund: str | None = None,
        inventory: str | None = None,
        case: str | None = None,
        archive_location: str | None = None,
        scan_file: str | list[str] | None = None,
        scan_content_type: str | None = None,
    ):
        self.catalog = catalog
        self.source_url = source_url
        self.original_text = original_text
        self.bibliography = bibliography
        # Structured archival provenance. `archive`/`fund`/`inventory`/`case`
        # mirror the metric-book naming (Архив/Фонд/Опись/Дело — gwar donesenie
        # cards). `archive_location` is a free-text shelf/box for catalogues
        # indexed that way instead (e.g. gwar gospital cards: "Шкаф б/н, ящик 49-А").
        self.archive = archive
        self.fund = fund
        self.inventory = inventory
        self.case = case
        self.archive_location = archive_location
        # Optional re-hosted SCAN of the source page. `scan_file` is a path
        # (relative to the village terraform module) to a local image/PDF that
        # the translator uploads as the geni_document's `file` body via
        # `filebase64("${path.module}/<scan_file>")` — used when the actual
        # scan reads better than a snapshot of `source_url` (e.g. the gwar.mil.ru
        # casualty-list page). `file` is mutually exclusive with `source_url` on
        # the provider (ExactlyOneOf), so the doc carries the scan and keeps the
        # source page URL only as a provenance line. `scan_content_type` is the
        # MIME type (provider accepts image/jpg|png|tif, application/pdf — note
        # `image/jpg`, NOT `image/jpeg`); defaults to image/jpg downstream.
        # A record may carry SEVERAL scans (e.g. a WWII award's приказ + the
        # наградной-лист pages) — each becomes its own geni_document. Accept a
        # single path or a list; `scan_files` is the normalized list, `scan_file`
        # the first (kept for single-scan callers).
        self.scan_files = [scan_file] if isinstance(scan_file, str) else list(scan_file or [])
        self.scan_file = self.scan_files[0] if self.scan_files else None
        self.scan_content_type = scan_content_type


class ExternalSourceRecord:
    """One person attested by one external catalog entry."""

    def __init__(
        self,
        person: Person,
        kind: ExternalSourceKind,
        citation: SourceCitation,
        *,
        record_number: int | str | None = None,
        age: int | str | None = None,
        birth_year: int | None = None,
        birth_date: EventDate | None = None,
        date: EventDate | None = None,
        page: str | None = None,
        rank: str | None = None,
        military_unit: str | None = None,
        casualty_reason: str | None = None,
        document_type: WwiDocumentType | WwiiDocumentType | None = None,
        award: str | None = None,
        award_number: str | int | None = None,
        marital_status: str | None = None,
        place_of_casualty: str | None = None,
        casualty_date: EventDate | None = None,
        draft_board: str | None = None,
        draft_date: EventDate | None = None,
        feat_date: EventDate | None = None,
        labels: list[str] | None = None,
        comment: str | None = None,
        reviewed: bool = True,
    ):
        self.person = person
        self.kind = kind
        self.citation = citation
        # `record_number` is the entry's own № in the source publication
        # (e.g. «12345» in the судимость gazette). `index` is a 1-based
        # positional fallback assigned by external_source_records() so
        # res_names stay unique when the source has no № (e.g. gwar cards).
        self.record_number = record_number
        self.index: int | None = None
        # Age as recorded in the source entry (e.g. «40 л.»).
        self.age = age
        self.birth_year = birth_year
        # A stated birth date (EventDate) — used by wwii_record, where cards
        # carry a real «Дата рождения»; preferred over `birth_year` when set.
        self.birth_date = birth_date
        # The event date as a single EventDate object (point or range).
        self.date = date
        # Page within the source — the printed gazette page (С. N) for
        # судимость, or the source's own page reference.
        self.page = page
        # WWI hero-card fields (gwar.mil.ru): rank/«звание», military unit,
        # casualty reason («причина выбытия»: болен/ранен/убит/…), and the
        # card/document type. Military-specific — only `wwi_record` sets them.
        self.rank = rank
        self.military_unit = military_unit
        self.casualty_reason = casualty_reason
        self.document_type = document_type
        # Award fields (gwar «Списки награжденных»): the decoration name
        # («награда», e.g. «Георгиевский крест IV-й степени») and its serial
        # «Номер награждения». ESC004 requires document_type=AWARD_LISTS.
        self.award = award
        self.award_number = award_number
        # Casualty/wounded card fields: marital status («женат/холост»), the
        # place of casualty/wounding («место выбытия», a battlefield/hospital
        # place distinct from the home village), and the casualty date («дата
        # выбытия») when it differs from the card's `date`. `casualty_date` is
        # descriptive only — `date` still drives the fatal-casualty death event.
        self.marital_status = marital_status
        self.place_of_casualty = place_of_casualty
        self.casualty_date = casualty_date
        # WWII (Память народа) card fields: the drafting military commissariat
        # («военкомат»), the draft date («дата призыва»), and the date of the
        # feat the award/casualty report describes («дата подвига»). WWI-only
        # today — no gwar equivalent.
        self.draft_board = draft_board
        self.draft_date = draft_date
        self.feat_date = feat_date
        self.labels = labels if labels is not None else list(_DEFAULT_LABELS[kind])
        self.comment = comment
        self.reviewed = reviewed

        # Auto-assign gender from the person's name when not already set,
        # mirroring births/deaths.
        if self.person and not self.person.gender:
            self.person.gender = get_gender_from_name(self.person.name_modern)

    @property
    def res_key(self) -> int | str:
        """Key used for res_name uniqueness: the source's own № when present,
        else the positional index assigned by `external_source_records()`."""
        if self.record_number is not None:
            return self.record_number
        return self.index if self.index is not None else 1

    # Start-of-event accessors — let the translator / village.db read the
    # leading date without unpacking the EventDate (ranges keep their end on
    # `self.date`).
    @property
    def event_year(self) -> int | None:
        return self.date.year if self.date else None

    @property
    def event_month(self) -> Month | None:
        return self.date.month if self.date else None

    @property
    def event_day(self) -> int | None:
        return self.date.day if self.date else None


class ExternalSourceRecords:
    """A village's collection of external-source records (one DSL file)."""

    def __init__(self, village: str, records: list[ExternalSourceRecord]):
        self.village = village
        self.records = records


def _external_source(
    person: Person,
    kind: ExternalSourceKind,
    *,
    verb: str,
    source_url: str,
    record_number: int | str | None = None,
    age: int | str | None = None,
    original_text: str | None = None,
    bibliography: str | None = None,
    birth_year: int | None = None,
    birth_date: EventDate | None = None,
    date: EventDate | None = None,
    page: str | None = None,
    archive: str | None = None,
    fund: str | None = None,
    inventory: str | None = None,
    case: str | None = None,
    archive_location: str | None = None,
    scan_file: str | list[str] | None = None,
    scan_content_type: str | None = None,
    rank: str | None = None,
    military_unit: str | None = None,
    casualty_reason: str | None = None,
    document_type: WwiDocumentType | WwiiDocumentType | None = None,
    award: str | None = None,
    award_number: str | int | None = None,
    marital_status: str | None = None,
    place_of_casualty: str | None = None,
    casualty_date: EventDate | None = None,
    draft_board: str | None = None,
    draft_date: EventDate | None = None,
    feat_date: EventDate | None = None,
    labels: list[str] | None = None,
    comment: str | None = None,
    reviewed: bool = True,
) -> ExternalSourceRecord:
    citation = SourceCitation(
        catalog=_CATALOG[kind],
        source_url=source_url,
        original_text=original_text,
        bibliography=bibliography,
        archive=archive,
        fund=fund,
        inventory=inventory,
        case=case,
        archive_location=archive_location,
        scan_file=scan_file,
        scan_content_type=scan_content_type,
    )
    card = ExternalSourceRecord(
        person,
        kind,
        citation,
        record_number=record_number,
        age=age,
        birth_year=birth_year,
        birth_date=birth_date,
        date=date,
        page=page,
        rank=rank,
        military_unit=military_unit,
        casualty_reason=casualty_reason,
        document_type=document_type,
        award=award,
        award_number=award_number,
        marital_status=marital_status,
        place_of_casualty=place_of_casualty,
        casualty_date=casualty_date,
        draft_board=draft_board,
        draft_date=draft_date,
        feat_date=feat_date,
        labels=labels,
        comment=comment,
        reviewed=reviewed,
    )
    setattr(card, VERB_ATTR, verb)   # which verb built it: `written` cannot tell the three apart
    return card


@captures_written
def criminal_record(
    person: Person,
    *,
    original_text: str,
    record_number: int | str | None = None,
    age: int | str | None = None,
    birth_year: int | None = None,
    date: EventDate | None = None,
    page: str | None = None,
    bibliography: str | None = None,
    source_url: str,
    archive: str | None = None,
    fund: str | None = None,
    inventory: str | None = None,
    case: str | None = None,
    scan_file: str | None = None,
    scan_content_type: str | None = None,
    labels: list[str] | None = None,
    comment: str | None = None,
    reviewed: bool = True,
) -> ExternalSourceRecord:
    """A судимость (criminal-record gazette) entry — «Ведомости справок о
    судимости 1870–1927». Requires the verbatim `original_text`. `record_number`
    is the entry's own № in the gazette (e.g. «12345»); `age` is the age it
    records — the birth year is derived from `age` + `date.year` unless an
    explicit `birth_year` override is given. `page` is the printed gazette page
    (С. N); `bibliography` (precise volume/page) and `source_url` (RSL
    digitised-gazette viewer link) come from familio's auth-gated fields.
    `scan_file` re-hosts the scanned gazette page (a local image/PDF) as the
    document body — Geni can't snapshot the RSL JS viewer, so the scan must be
    uploaded."""
    return _external_source(
        person,
        ExternalSourceKind.CRIMINAL,
        verb="criminal_record",
        source_url=source_url,
        record_number=record_number,
        age=age,
        original_text=original_text,
        bibliography=bibliography,
        archive=archive,
        fund=fund,
        inventory=inventory,
        case=case,
        scan_file=scan_file,
        scan_content_type=scan_content_type,
        birth_year=birth_year,
        date=date,
        page=page,
        labels=labels,
        comment=comment,
        reviewed=reviewed,
    )


@captures_written
def wwi_record(
    person: Person,
    *,
    source_url: str,
    record_number: int | str | None = None,
    age: int | str | None = None,
    birth_year: int | None = None,
    original_text: str | None = None,
    date: EventDate | None = None,
    page: str | None = None,
    rank: str | None = None,
    military_unit: str | None = None,
    casualty_reason: str | None = None,
    document_type: WwiDocumentType | WwiiDocumentType | None = None,
    award: str | None = None,
    award_number: str | int | None = None,
    marital_status: str | None = None,
    place_of_casualty: str | None = None,
    casualty_date: EventDate | None = None,
    archive: str | None = None,
    fund: str | None = None,
    inventory: str | None = None,
    case: str | None = None,
    archive_location: str | None = None,
    scan_file: str | None = None,
    scan_content_type: str | None = None,
    bibliography: str | None = None,
    labels: list[str] | None = None,
    comment: str | None = None,
    reviewed: bool = True,
) -> ExternalSourceRecord:
    """A военная служба (WWI participant) entry — gwar.mil.ru hero card.
    Requires the `source_url` to the card. Card fields when known: `rank`
    («должность/звание»), `military_unit` («воинская часть»), `casualty_reason`
    («причина выбытия» — a fatal one, убит/умер/погиб, emits a death event),
    `document_type` («тип документа», a `WwiDocumentType` member — casualty_reason
    on an award document is rejected by ESC003), a `date` («дата события», may be a
    range), and archival provenance `archive` (РГВИА), `fund`, `inventory`
    (опись), `case` (дело) or `archive_location` («шкаф/ящик»); plus
    `record_number`/`age`/birth year. Award cards («Списки награжденных») carry
    `award` («награда») and `award_number` («Номер награждения») — both require
    `document_type=AWARD_LISTS` (ESC004). Casualty/wounded cards carry
    `marital_status` («женат/холост»), `place_of_casualty` («место выбытия» — the
    battlefield/hospital place, distinct from the home village) and, when it
    differs from `date`, `casualty_date` («дата выбытия», descriptive only — `date`
    still drives the fatal-casualty death event). Pre-war occupation («занятие
    перед войной») is carried on `person(occupation=…)`. `scan_file` re-hosts the
    actual scanned page (a local image/PDF) as the document body instead of
    snapshotting `source_url` — see SourceCitation."""
    return _external_source(
        person,
        ExternalSourceKind.WWI,
        verb="wwi_record",
        source_url=source_url,
        record_number=record_number,
        age=age,
        original_text=original_text,
        bibliography=bibliography,
        birth_year=birth_year,
        date=date,
        page=page,
        rank=rank,
        military_unit=military_unit,
        casualty_reason=casualty_reason,
        document_type=document_type,
        award=award,
        award_number=award_number,
        marital_status=marital_status,
        place_of_casualty=place_of_casualty,
        casualty_date=casualty_date,
        archive=archive,
        fund=fund,
        inventory=inventory,
        case=case,
        archive_location=archive_location,
        scan_file=scan_file,
        scan_content_type=scan_content_type,
        labels=labels,
        comment=comment,
        reviewed=reviewed,
    )


@captures_written
def wwii_record(
    person: Person,
    *,
    source_url: str,
    record_number: int | str | None = None,
    age: int | str | None = None,
    birth_date: EventDate | None = None,
    original_text: str | None = None,
    date: EventDate | None = None,
    page: str | None = None,
    rank: str | None = None,
    military_unit: str | None = None,
    casualty_reason: str | None = None,
    document_type: WwiDocumentType | WwiiDocumentType | None = None,
    award: str | None = None,
    award_number: str | int | None = None,
    marital_status: str | None = None,
    place_of_casualty: str | None = None,
    casualty_date: EventDate | None = None,
    draft_board: str | None = None,
    draft_date: EventDate | None = None,
    feat_date: EventDate | None = None,
    archive: str | None = None,
    fund: str | None = None,
    inventory: str | None = None,
    case: str | None = None,
    archive_location: str | None = None,
    scan_file: str | list[str] | None = None,
    scan_content_type: str | None = None,
    bibliography: str | None = None,
    labels: list[str] | None = None,
    comment: str | None = None,
    reviewed: bool = True,
) -> ExternalSourceRecord:
    """A Великая Отечественная война entry — a pamyat-naroda.ru/podvignaroda.ru
    card. Requires the `source_url` to the card. Card fields map from the
    card's own labels: «Воинское звание» → `rank`, «Место службы» →
    `military_unit`, «Наименование награды» → `award`, «Номер документа» →
    `award_number`, «Дата призыва» → `draft_date`, and the drafting commissariat
    («военкомат») → `draft_board`. `document_type` («тип документа», a
    `WwiiDocumentType` member) selects the card kind — award documents
    (наградной лист / приказ о награждении / юбилейная картотека) carry
    `award`/`award_number` (ESC004) and reject `casualty_reason` (ESC003); a
    fatal `casualty_reason` («убит»/«умер»/«погиб» — from a донесение о
    безвозвратных потерях) emits a death event dated to `date`, mirroring
    `wwi_record`. `feat_date` («дата подвига») is the date of the citation's
    described feat, when it differs from `date`. Archival provenance mirrors
    `wwi_record`: `archive` (ЦАМО), `fund`, `inventory` (опись), `case` (дело)
    or `archive_location` («шкаф/ящик»). `scan_file` re-hosts the actual
    scanned page (a local image/PDF) as the document body — pamyat-naroda.ru
    and podvignaroda.ru are anti-bot just like gwar.mil.ru, so Geni's
    `source_url` snapshotter can't reach them either."""
    return _external_source(
        person,
        ExternalSourceKind.WWII,
        verb="wwii_record",
        source_url=source_url,
        record_number=record_number,
        age=age,
        original_text=original_text,
        bibliography=bibliography,
        birth_date=birth_date,
        date=date,
        page=page,
        rank=rank,
        military_unit=military_unit,
        casualty_reason=casualty_reason,
        document_type=document_type,
        award=award,
        award_number=award_number,
        marital_status=marital_status,
        place_of_casualty=place_of_casualty,
        casualty_date=casualty_date,
        draft_board=draft_board,
        draft_date=draft_date,
        feat_date=feat_date,
        archive=archive,
        fund=fund,
        inventory=inventory,
        case=case,
        archive_location=archive_location,
        scan_file=scan_file,
        scan_content_type=scan_content_type,
        labels=labels,
        comment=comment,
        reviewed=reviewed,
    )


@captures_written
def external_source_records(
    village: str,
    *records: ExternalSourceRecord,
) -> ExternalSourceRecords:
    """Collect external-source records for a village (one DSL file).

    Unlike the metric-book `*_records()` factories there is no `defaults`
    argument — external-source records carry their own status and residence
    on the `person()`. Assigns each record a 1-based positional `index` for
    res_name uniqueness (used when the source has no own № — see `res_key`)."""
    recs = list(records)
    for i, rec in enumerate(recs, start=1):
        rec.index = i
    return ExternalSourceRecords(village, recs)
