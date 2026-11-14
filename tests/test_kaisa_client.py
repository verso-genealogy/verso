"""Reading a лист number off a КАИСА scan filename, and finding it without a full sweep.

The archive names every scan itself, and that name is the ONLY place a лист number
appears. ГАВО writes it in five different shapes depending on the digitisation batch,
and the failure mode of getting it wrong is silent: a parser that understands one
shape does not raise on the others, it points at another parish's листы. That is not
theoretical — an earlier run pulled the scans of neighbouring parishes before anyone
noticed, because a spread (`0050(037об-038).tif`) was read as "no лист here".

So this pins the shapes, and pins that `locate` walks a дело by binary search rather
than harvesting all 300–2000 notes to fetch thirty images.
"""
import pytest

from verso.ru.archives.kaisa import (
    GATO, GAVO, Client, Delo, LocateError, deobfuscate, folio_index, folio_span, obfuscate, pages_for, parse_spec, scan_filename)


class TestFolioSpan:
    @pytest.mark.parametrize(("name", "first", "last"), [
        ("0094_051.jpg", 51, 51),                     # ГАВО ф.123 оп.4 — one side
        ("1088_585 об.jpg", 585, 585),                # …with a space before «об»
        ("0011_004а.jpg", 4, 4),                      # литерный лист
        ("0050(037об-038).tif", 37, 38),              # ф.123 — a SPREAD
        ("049_(043об-044).jpg", 43, 44),              # …with both separators
        ("0150(131об).tif", 131, 131),                # single side in parens
        ("002об-003.jpg", 2, 3),                      # the лист alone, no page prefix
        ("001об.jpg", 1, 1),
        ("ГАВО_Ф123Оп4Д5Л017.tif", 17, 17),        # лист behind a «Л» marker
    ])
    def test_reads_every_shape(self, name: str, first: int, last: int) -> None:
        span = folio_span(name)
        assert span is not None, name
        assert (span[0][0], span[1][0]) == (first, last)

    @pytest.mark.parametrize("name", [
        "0001(обложка).tif",
        "0299(лист-заверитель).tif",
        "002_(ОБЛ-1).jpg",                            # ← has a digit, is not a лист
        "ГАВО_Ф123Оп4Д5_Титульный лист_1.tif",
        "0028.jpg",                                   # a scan number, not a лист
    ])
    def test_refuses_what_carries_no_folio(self, name: str) -> None:
        assert folio_span(name) is None

    def test_bare_number_is_a_folio_only_on_evidence(self) -> None:
        """`001.jpg` is лист 1 in a дело that names files by лист — and nowhere else.

        Deciding this per-дело is the whole point: guessing "yes" turns every
        sequence-numbered scan into a лист, and guessing "no" loses the rectos of a
        дело whose versos read `002об-003.jpg`.
        """
        assert folio_span("001.jpg") is None
        span = folio_span("001.jpg", bare_is_folio=True)
        assert span is not None and span[0][0] == 1

    def test_spread_marks_verso_of_the_first_folio(self) -> None:
        span = folio_span("0050(037об-038).tif")
        assert span == ((37, 0, 1), (38, 0, 0))


class TestSpecAndIndex:
    def test_parses_ranges_and_lists(self) -> None:
        assert parse_spec("51-119") == [(51, 119)]
        assert parse_spec("51,53,60-64") == [(51, 51), (53, 53), (60, 64)]

    def test_rejects_nonsense(self) -> None:
        with pytest.raises(LocateError):
            parse_spec("сорок первый")

    def test_index_puts_a_spread_under_both_folios(self) -> None:
        idx = folio_index({7: "0050(037об-038).tif", 8: "0051(038об-039).tif"})
        assert idx["37"] == [7]
        assert idx["38"] == [7, 8]          # лист 38 is split across two scans
        assert idx["39"] == [8]

    def test_pages_for_takes_every_scan_touching_the_range(self) -> None:
        notes = {5: "0005(001об-002).tif", 6: "0006(002об-003).tif",
                 7: "0007(003об-004).tif", 8: "0008(004об-005).tif"}
        assert pages_for("3", notes, 8) == [6, 7]
        assert pages_for("all", notes, 8) == [1, 2, 3, 4, 5, 6, 7, 8]


class TestViewerUrls:
    def test_obfuscation_round_trips(self) -> None:
        """Viewer URLs are base64 over the query string XORed with 0xFF."""
        params = "filename=image.jpg&currentPage=1&serial=2&size=5"
        assert deobfuscate(obfuscate(params)) == params

    def test_survives_the_quotes_the_api_wraps_urls_in(self) -> None:
        params = "currentPage=7&serial=9"
        assert deobfuscate(f"'{obfuscate(params)}'") == params


class _FakeClient(Client):
    """A Client whose notes come from a dict, so locate() can be tested offline."""

    def __init__(self, notes: dict[int, str]) -> None:
        super().__init__(GAVO, "Bearer test")
        self._notes = notes
        self.probes = 0

    def note(self, url: str, tries: int = 4) -> str:
        self.probes += 1
        return self._notes.get(int(url), "")


def _delo(pages: int) -> Delo:
    return Delo(code="Ф. 978 Оп. 658 Д. 95", object_id=1, title=None, dates=None,
                folios=None, urls=[str(p) for p in range(1, pages + 1)])


class TestLocate:
    def _spreads(self, pages: int) -> dict[int, str]:
        # page 1 обложка, page 2 внутр. опись, then лист 1об-2, 2об-3, …
        notes = {1: "0001(обложка).tif", 2: "0002(внутр оп 1).tif"}
        for page in range(3, pages + 1):
            n = page - 2
            notes[page] = f"{page:04d}({n:03d}об-{n + 1:03d}).tif"
        return notes

    def test_finds_the_range_without_reading_every_note(self) -> None:
        notes = self._spreads(600)
        client = _FakeClient(notes)
        pages, _ = client.locate("100-103", _delo(600))
        assert pages_for("100-103", notes, 600) == pages
        # the point of the binary search: a handful of probes, not 600
        assert client.probes < 40

    def test_refuses_a_дело_whose_names_carry_no_folio(self) -> None:
        """Better to stop than to walk: this is the case that downloaded half a дело."""
        client = _FakeClient({p: f"{p:04d}.jpg" for p in range(1, 401)})
        with pytest.raises(LocateError):
            client.locate("39-40", _delo(400))

    def test_empty_viewer_means_no_active_subscription(self) -> None:
        client = _FakeClient({})
        with pytest.raises(LocateError, match="абонемент"):
            client.locate("1-2", _delo(0))


class TestInstances:
    def test_the_two_archives_differ_only_in_configuration(self) -> None:
        assert GATO.host != GAVO.host
        assert GATO.object_type != GAVO.object_type
        assert GATO.viewer_ext == ".pdf" and GAVO.viewer_ext == ".jpg"
        # ГАТО keys the file group per дело; ГАВО returns an empty group and needs a seed
        assert GATO.viewer_serial_seed is None and GAVO.viewer_serial_seed == 2

    def test_bearer_prefix_is_added_only_where_the_token_lacks_it(self) -> None:
        assert Client(GATO, "eyJhbGciOi")._auth == "Bearer eyJhbGciOi"
        assert Client(GAVO, "Bearer eyJhbGciOi")._auth == "Bearer eyJhbGciOi"
        assert Client(GATO, "Bearer eyJhbGciOi")._auth == "Bearer eyJhbGciOi"


class TestScanFilename:
    """The archive names its TIFF master; the viewer serves JPEG. The file on disk
    must say what it actually is — Apple Photos rejects a JPEG called .tif and the
    modal it raises blocks every further write to the library."""

    def test_keeps_the_folio_and_fixes_the_extension(self) -> None:
        assert scan_filename("0188(169).tif", 7) == "0188(169).jpg"
        assert scan_filename("ГАВО_Ф123Оп4Д5Л017.tif", 7) == "ГАВО_Ф123Оп4Д5Л017.jpg"

    def test_leaves_a_correct_name_alone(self) -> None:
        assert scan_filename("0094_051.jpg", 7) == "0094_051.jpg"

    def test_falls_back_to_the_page_number(self) -> None:
        assert scan_filename(None, 7) == "0007.jpg"
        assert scan_filename("", 7) == "0007.jpg"
