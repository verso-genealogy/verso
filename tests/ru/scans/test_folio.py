from __future__ import annotations

import unittest

from verso.ru.scans.folio import (Page, check_album, format_report, frame_pages, expand_spreads, parse_album, parse_frame, parse_name)

# How an album looks when it was never renamed: straight off the phone.
PHONE_NAMES = ["IMG_20000101_120000.jpg", "IMG_20000101_120012.jpg",
               "IMG_20000101_120030.jpg"]


def album(first: int, last: int, *, start_frame: int = 118, cover: bool = True) -> list[str]:
    names = ["001_обложка.jpg"] if cover else []
    frame = start_frame
    for number in range(first, last + 1):
        names.append(f"{frame}_{number}.jpg")
        names.append(f"{frame + 1}_{number}об.jpg")
        frame += 2
    return names


class ParseName(unittest.TestCase):
    def test_recto(self):
        self.assertEqual(Page(57, "", False, 118, "118_57.jpg"), parse_name("118_57.jpg"))

    def test_verso(self):
        page = parse_name("119_57об.jpg")
        assert page is not None
        self.assertTrue(page.verso)
        self.assertEqual("57об", page.label)

    def test_cover_has_no_folio(self):
        page = parse_name("001_обложка.jpg")
        assert page is not None
        self.assertFalse(page.is_folio)
        self.assertEqual(1, page.frame)

    def test_inventory_frame_has_no_folio(self):
        page = parse_name("002_внутр оп.jpg")
        assert page is not None
        self.assertFalse(page.is_folio)

    def test_extension_is_case_insensitive(self):
        self.assertIsNotNone(parse_name("118_57.JPG"))

    def test_unrelated_name_is_rejected(self):
        self.assertIsNone(parse_name("notes.txt"))
        self.assertIsNone(parse_name("scan.jpg"))


class LetteredLeaves(unittest.TestCase):
    """An archivist binds a leaf in later and numbers it 12а; the photographer
    types the verso as `12а об`, with a space. Both shapes occur in one
    album, and dropping them silently loses two pages."""

    def test_letter_suffix(self):
        page = parse_name("74_012а.jpg")
        assert page is not None
        self.assertEqual((12, "а", False), (page.number, page.letter, page.verso))
        self.assertEqual("12а", page.label)

    def test_letter_suffix_verso_with_a_space(self):
        page = parse_name("75_012а об.jpg")
        assert page is not None
        self.assertEqual("12а об".replace(" ", ""), page.label)
        self.assertTrue(page.verso)

    def test_leading_zeros_are_dropped(self):
        page = parse_name("76_013.jpg")
        assert page is not None
        self.assertEqual(13, page.number)

    def test_a_lettered_leaf_sorts_after_its_plain_one(self):
        pages, _ = parse_album(["1_13.jpg", "2_12а.jpg", "3_12.jpg"])
        self.assertEqual(["12", "12а", "13"], [p.label for p in pages])

    def test_opening_on_a_lettered_leaf_does_not_claim_the_plain_one(self):
        # The album starts at 12а; л. 12 belongs to the previous year's album,
        # and reporting it missing would be noise.
        names = ["74_012а.jpg", "75_012а об.jpg"] + album(13, 16, start_frame=76,
                                                            cover=False)
        report = check_album(names)
        self.assertEqual((), report.missing_pages)
        self.assertEqual("12а", report.first_label)
        self.assertEqual(13, report.first_folio)
        self.assertTrue(report.ok)


class Ordering(unittest.TestCase):
    def test_reading_order_is_recto_then_verso(self):
        pages, _ = parse_album(["119_57об.jpg", "120_58.jpg", "118_57.jpg"])
        self.assertEqual(["57", "57об", "58"], [p.label for p in pages])

    def test_cover_sorts_first(self):
        pages, _ = parse_album(["118_57.jpg", "001_обложка.jpg"])
        self.assertFalse(pages[0].is_folio)

    def test_unparseable_names_are_reported_not_dropped(self):
        _, bad = parse_album(["118_57.jpg", "readme.txt"])
        self.assertEqual(["readme.txt"], bad)


class CheckAlbum(unittest.TestCase):
    """An album of лл. 57–92об, cover, no gaps."""

    def test_complete_album_is_ok(self):
        report = check_album(album(57, 92), expect_first=57, expect_last=92)
        self.assertTrue(report.ok)
        self.assertEqual((57, 92), (report.first_folio, report.last_folio))

    def test_a_missing_side_is_named(self):
        names = [n for n in album(57, 92) if not n.endswith("_64об.jpg")]
        report = check_album(names)
        self.assertEqual(("64об",), report.missing_pages)
        self.assertFalse(report.ok)

    def test_a_doubled_page_is_named(self):
        names = album(57, 92) + ["999_64.jpg"]
        report = check_album(names)
        self.assertEqual(("64",), report.duplicate_pages)

    def test_a_leaf_from_another_year_is_flagged(self):
        # A failure an album once had: a leaf of another year filed into it,
        # invisible until the year had been read once.
        report = check_album(album(57, 92) + ["500_30.jpg"],
                             expect_first=57, expect_last=92)
        self.assertEqual(("30",), report.outside_range)
        self.assertFalse(report.ok)

    def test_declared_range_is_optional(self):
        self.assertEqual((), check_album(album(57, 92)).outside_range)

    def test_frame_gaps_are_informational_only(self):
        # The cover is frame 1 and the first leaf is frame 118; that gap is
        # normal and must not make the album look broken.
        report = check_album(album(57, 92))
        self.assertTrue(report.frame_gaps)
        self.assertTrue(report.ok)

    def test_empty_directory(self):
        report = check_album([])
        self.assertIsNone(report.first_folio)


class Report(unittest.TestCase):
    def test_clean_album_says_continuous(self):
        text = format_report(check_album(album(57, 92)), album="Маниловка 1900")
        self.assertIn("лл. 57–92об", text)
        self.assertIn("✅", text)

    def test_wrong_year_leaf_is_loud(self):
        text = format_report(check_album(album(57, 92) + ["500_30.jpg"],
                                         expect_first=57, expect_last=92))
        self.assertIn("wrong year", text)

    def test_no_folios_at_all(self):
        text = format_report(check_album(["001_обложка.jpg"]))
        self.assertIn("no folio numbering to check", text)
        self.assertIn("1 file(s)", text)

    def test_unrenamed_album_is_told_what_to_do(self):
        # Albums sit in a photo library exactly as the phone wrote them,
        # and the old message ("no folio frames found.") said nothing about the
        # frame fallback — which is why the tool looked broken rather than
        # limited.
        text = format_report(check_album(PHONE_NAMES))
        self.assertIn("3 file(s)", text)
        self.assertIn("IMG_20000101_120000.jpg", text)
        self.assertIn("by FRAME", text)
        self.assertIn("Rename the album", text)


class FramePages(unittest.TestCase):
    def test_position_becomes_the_frame(self):
        pages = frame_pages(PHONE_NAMES)
        self.assertEqual([1, 2, 3], [p.frame for p in pages])
        self.assertEqual(["кадр1", "кадр2", "кадр3"], [p.label for p in pages])

    def test_order_is_by_filename_not_by_argument_order(self):
        pages = frame_pages(list(reversed(PHONE_NAMES)))
        self.assertEqual([n for n in PHONE_NAMES], [p.name for p in pages])

    def test_no_page_claims_a_folio(self):
        self.assertFalse(any(p.is_folio for p in frame_pages(PHONE_NAMES)))

    def test_a_cover_is_labelled_by_frame_too(self):
        page = parse_name("001_обложка.jpg")
        assert page is not None
        self.assertEqual("кадр1", page.label)


if __name__ == "__main__":
    unittest.main()


class SpreadFrameNames(unittest.TestCase):
    """An archive's album of spreads: one frame is a whole spread and the name says both leaves.

    Before this the albums fell through to `frame_pages`, where continuity is
    unverifiable and `spread` does not apply — while the лист numbering was
    sitting in the filename the whole time.
    """

    def test_single_leaf_in_parentheses(self):
        pages = parse_frame("0240(131).jpg")
        self.assertEqual(1, len(pages))
        self.assertEqual((131, False, 240, ""), (pages[0].number, pages[0].verso,
                                                 pages[0].frame, pages[0].half))

    def test_spread_yields_both_leaves(self):
        verso, recto = parse_frame("0241(131об-132).jpg")
        self.assertEqual(("131об", True, "L"), (verso.label, verso.verso, verso.half))
        self.assertEqual(("132", False, "R"), (recto.label, recto.verso, recto.half))
        self.assertEqual(241, verso.frame)
        self.assertEqual(verso.frame, recto.frame)

    def test_underscore_before_parenthesis(self):
        verso, recto = parse_frame("305_(144об-145).jpg")
        self.assertEqual(("144об", "145"), (verso.label, recto.label))

    def test_album_of_spreads_is_continuous(self):
        # 131 alone, then spreads: every side of 131–133 is present.
        # Spreads pair a verso with the NEXT recto, so a run is only whole
        # when the album opens on a lone recto and closes on a lone verso.
        names = ["0240(131).jpg", "0241(131об-132).jpg",
                 "0242(132об-133).jpg", "0243(133об).jpg"]
        report = check_album(names)
        self.assertEqual((), report.missing_pages)
        self.assertEqual((), report.unparseable)
        self.assertEqual("131", report.first_label)
        self.assertEqual("133об", report.last_label)

    def test_a_spread_album_cut_mid_leaf_reports_the_open_side(self):
        # Ending on a recto leaves its verso unaccounted for, and saying so is
        # the point: on a spread album the tail of the range is exactly where a
        # frame goes missing without the folio numbering skipping.
        names = ["0240(131).jpg", "0241(131об-132).jpg", "0242(132об-133).jpg"]
        self.assertEqual(("133об",), check_album(names).missing_pages)

    def test_a_missing_spread_is_still_caught(self):
        names = ["0240(131).jpg", "0242(132об-133).jpg"]
        self.assertIn("131об", check_album(names).missing_pages)

    def test_spread_without_parentheses(self):
        # `612_388об-389.jpg` — an album writes the same spread with no
        # brackets, and the frame number (612) is nothing like either лист.
        verso, recto = parse_frame("612_388об-389.jpg")
        self.assertEqual(("388об", "L", 612), (verso.label, verso.half, verso.frame))
        self.assertEqual(("389", "R", 612), (recto.label, recto.half, recto.frame))

    def test_a_hyphen_that_is_not_a_spread_is_left_alone(self):
        # Only a pair of readable folios makes a spread; anything else stays
        # the single page (or the label-less frame) it already was.
        self.assertEqual(["кадр2"], [p.label for p in parse_frame("002_внутр оп.jpg")])
        self.assertEqual(["57об"], [p.label for p in parse_frame("118_57об.jpg")])

    def test_bare_folio_names(self):
        # `83об.jpg` — the лист and nothing else, how some albums are named. No
        # frame number exists to compare against, so continuity rests on the
        # folios alone.
        self.assertEqual(["83об"], [p.label for p in parse_frame("83об.jpg")])
        self.assertEqual(["47"], [p.label for p in parse_frame("047.jpg")])
        self.assertEqual([], parse_frame("!!обложка.jpg"))

    def test_bare_folio_album_gets_frames_from_reading_order(self):
        pages, bad = parse_album(["048об.jpg", "047.jpg", "048.jpg"])
        self.assertEqual(["47", "48", "48об"], [p.label for p in pages])
        self.assertEqual([1, 2, 3], [p.frame for p in pages])
        self.assertEqual([], bad)

    def test_unreadable_folio_in_parentheses_is_not_a_page(self):
        self.assertEqual([], parse_frame("0300(обложка).jpg"))


class SpreadsDeclaredPerAlbum(unittest.TestCase):
    """`frames = "spread"`: the file is a spread, the NAME gives one лист.

    Some albums name a frame by its left leaf, so every recto is
    invisible — missing from the report and impossible to address — until the
    album says it is shot this way.
    """

    def test_a_verso_file_yields_the_facing_recto(self):
        pages, _ = parse_album(["83об.jpg"])
        self.assertEqual([("83об", "L"), ("84", "R")],
                         [(p.label, p.half) for p in expand_spreads(pages)])

    def test_a_recto_file_yields_its_own_verso(self):
        pages, _ = parse_album(["047.jpg"])
        self.assertEqual([("47", "L"), ("47об", "R")],
                         [(p.label, p.half) for p in expand_spreads(pages)])

    def test_a_page_whose_facing_side_has_its_own_file_is_left_alone(self):
        # These albums MIX: the opening leaves are single frames, the rest are
        # spreads. Expanding a single frame would invent a second copy of a
        # side the album already holds.
        pages, _ = parse_album(["048.jpg", "048об.jpg"])
        self.assertEqual([("48", ""), ("48об", "L"), ("49", "R")],
                         [(p.label, p.half) for p in expand_spreads(pages)])

    def test_pages_that_already_name_both_leaves_are_untouched(self):
        pages, _ = parse_album(["0241(131об-132).jpg"])
        self.assertEqual(expand_spreads(pages), pages)

    def test_a_cover_is_not_expanded(self):
        pages, _ = parse_album(["001_обложка.jpg"])
        self.assertEqual(expand_spreads(pages), pages)

    def test_expanding_leaves_no_duplicate_side(self):
        pages, _ = parse_album(["047.jpg", "048.jpg", "048об.jpg", "83об.jpg"])
        expanded = expand_spreads(pages)
        self.assertEqual(len({p.key for p in expanded}), len(expanded))

    def test_a_frame_that_shows_one_page_is_left_alone(self):
        # An album shot its blank leaves 31 and 31а standing up among
        # spreads: split, 31 opened on half its own page and 31об went to both.
        pages, _ = parse_album(["087_(029об-030).jpg", "088_(031).jpg", "089_(031а).jpg"])
        standing = {"088_(031).jpg", "089_(031а).jpg"}
        expanded = expand_spreads(pages, lambda page: page.name in standing)
        self.assertEqual([("29об", "L"), ("30", "R"), ("31", ""), ("31а", "")],
                         [(p.label, p.half) for p in expanded])
        # Read by name alone they were split, and two frames carried 31об.
        self.assertEqual(["31", "31об", "31об", "31а"],
                         [p.label for p in expand_spreads(pages) if p.name != "087_(029об-030).jpg"])


class ATimestampIsNotAFolio(unittest.TestCase):
    """`20000102_120039.jpg` is a phone's timestamp, not кадр 20000102 л. 120039.

    Unrenamed albums are named this way, and the shape collides exactly with
    the archive's `<кадр>_<лист>.jpg`. Read as a лист, it made `check` report
    hundreds of absent pages, and — the expensive part — made `exported_name` believe
    the filename already carried a лист, so the «Название» the reader had just
    set in Photos was ignored and the export came out under the timestamps
    again.
    """

    def test_a_six_digit_folio_is_not_a_folio(self):
        # The frame parses (it has a frame number) but carries NO лист: that is
        # the same shape as a cover, and `number == 0` is how it says so.
        [page] = parse_frame("20000102_120039.jpg")
        self.assertEqual(0, page.number)

    def test_a_real_folio_still_parses(self):
        [page] = parse_frame("0005_144.jpg")
        self.assertEqual((5, 144), (page.frame, page.number))

    def test_the_largest_plausible_folio_still_parses(self):
        [page] = parse_frame("0001_9999.jpg")
        self.assertEqual(9999, page.number)

    def test_a_verso_of_a_deep_дело_still_parses(self):
        [page] = parse_frame("0900_1234об.jpg")
        self.assertEqual((1234, True), (page.number, page.verso))


class RenumberScans(unittest.TestCase):
    """An ЭЧЗ download named by scan number, relabelled by лист."""

    def setUp(self):
        self.pages, _ = parse_album([f"{n}.jpg" for n in range(3001, 3118)])

    def test_one_side_per_scan_from_the_first_leaf(self):
        from verso.ru.scans.folio import renumber_scans
        labels = {p.name: p.label for p in renumber_scans(self.pages, 3001, "200")}
        # A revision list: скан 3001 is л. 200, скан 3032 л. 215об.
        self.assertEqual(("200", "200об", "215об", "216"),
                         (labels["3001.jpg"], labels["3002.jpg"], labels["3032.jpg"], labels["3033.jpg"]))

    def test_a_first_scan_on_a_verso(self):
        from verso.ru.scans.folio import renumber_scans
        labels = [p.label for p in renumber_scans(self.pages[:3], 3001, "12об")]
        self.assertEqual(["12об", "13", "13об"], labels)

    def test_a_scan_before_the_first_is_left_alone(self):
        from verso.ru.scans.folio import renumber_scans
        labels = [p.label for p in renumber_scans(self.pages[:3], 3002, "200")]
        self.assertEqual(["200", "200об", "3001"], labels)
