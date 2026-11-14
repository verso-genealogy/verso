def _book_datetime(year: int, month: int, day: int):
    """A `datetime` ORDERING key for a date as the book wrote it.

    The metric books are Julian: every fourth year is a leap year, 1700, 1800
    and 1900 included. `datetime` is proleptic Gregorian, where those three are
    common years, so it rejects 29 February of them — and a burial record of
    1800 is dated exactly that. The key sits at NOON on the 28th: strictly
    after the 28th and before 1 March, which is all `_pick_best_date` asks of
    it (ordering, and gaps measured in tens of weeks). The date written to
    terraform is the DSL's own `day`/`month`, never this key.

    Nothing else is tolerated. 31 November, or 29 February in a Julian common
    year, is a transcription error, and the crash is how it gets noticed.
    """
    from datetime import datetime
    try:
        return datetime(year=year, month=month, day=day)
    except ValueError:
        if (month, day) == (2, 29) and year % 4 == 0:
            return datetime(year=year, month=2, day=28, hour=12)
        raise


class GeniDate:
    def __init__(self,
                 day=None,
                 month=None,
                 year=None,
                 circa: bool = False,
                 end_day=None,
                 end_month=None,
                 end_year=None,
                 end_circa: bool = False,
                 date_range: str | None = None,
                 synthetic: bool = False):
        self.day = int(day) if day and day != '?' and day != '??' else None
        self.month = int(month) if month and month != '?' else None
        self.year = int(year) if year and year != '?' else None
        self.circa = circa
        self.end_day = int(end_day) if end_day and end_day != '?' else None
        self.end_month = int(end_month) if end_month and end_month != '?' else None
        self.end_year = int(end_year) if end_year and end_year != '?' else None
        self.end_circa = end_circa
        self.date_range = date_range
        # True for a DERIVED bound — today only the parent-birth estimate in
        # `verso.ru.targets.geni.translator.birth_estimates`, computed from a
        # relative's date rather than read off a record. Never emitted to
        # terraform; it exists so `_pick_best_date` can refuse to let a
        # derived bound override or widen a date that came from an actual
        # source. (The godparent/witness adult windows are estimates too, but
        # stay unmarked for legacy merge parity.)
        self.synthetic = synthetic

    def to_terraform(self, indent: str = "") -> str:
        """Render `{ <fields> }` block with `terraform fmt`-style alignment.

        `indent` is the column offset of the line that contains the opening
        `{`; body lines get `indent + "  "`, the closing `}` is at `indent`.
        Field padding aligns the `=` column to the widest key actually
        present (not all possible keys), matching what `terraform fmt`
        produces — so post-fmt re-runs are idempotent.
        """
        fields: list[tuple[str, str]] = []
        if self.date_range:
            fields.append(("range", f'"{self.date_range}"'))
        if self.circa:
            fields.append(("circa", str(self.circa).lower()))
        if self.day:
            fields.append(("day", str(self.day)))
        if self.month:
            fields.append(("month", str(self.month)))
        if self.year:
            fields.append(("year", str(self.year)))
        if self.end_circa:
            fields.append(("end_circa", str(self.end_circa).lower()))
        if self.end_day:
            fields.append(("end_day", str(self.end_day)))
        if self.end_month:
            fields.append(("end_month", str(self.end_month)))
        if self.end_year:
            fields.append(("end_year", str(self.end_year)))
        if not fields:
            return "{}"
        width = max(len(k) for k, _ in fields)
        inner = indent + "  "
        lines = [f"{inner}{k.ljust(width)} = {v}" for k, v in fields]
        return "{\n" + "\n".join(lines) + f"\n{indent}}}"

    def to_datetime(self):
        from datetime import datetime
        if self.year is None:
            return None
        if self.month is None:
            return datetime(year=self.year, month=1, day=1)
        if self.day is None:
            return datetime(year=self.year, month=self.month, day=1)
        return _book_datetime(self.year, self.month, self.day)

    def to_end_datetime(self):
        from datetime import datetime
        if self.end_year is None:
            return None
        # Year-only end: semantically "end of <end_year>", so use Dec 31.
        # `to_datetime()` symmetrically uses Jan 1 for year-only starts.
        # This makes range widths and gap-arithmetic in
        # `_pick_best_date` reflect the calendar span the end_year
        # is meant to cover, instead of a Jan-1-to-Jan-1 underestimate.
        if self.end_month is None:
            return datetime(year=self.end_year, month=12, day=31)
        if self.end_day is None:
            # Month-only end: last day of that month. Use day 28 as a
            # conservative lower bound that's correct for every month
            # (matches the start-of-month semantics in to_datetime()
            # being a 1-day-precision underestimate).
            return datetime(year=self.end_year, month=self.end_month, day=28)
        return _book_datetime(self.end_year, self.end_month, self.end_day)

    def __eq__(self, other):
        if not isinstance(other, GeniDate):
            return NotImplemented
        return (self.day, self.month, self.year) == (other.day, other.month, other.year)

    def __str__(self):
        return f"GeniDate(day={self.day}, month={self.month}, year={self.year}, circa={self.circa}, " \
               f"{self.end_day}, end_month={self.end_month}, end_year={self.end_year}, end_circa={self.end_circa}, range={self.date_range})"
