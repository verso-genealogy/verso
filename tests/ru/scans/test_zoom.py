"""The second reading tier's geometry: which box `--col`/`--row`/`--box` mean."""
from __future__ import annotations

import pytest

from verso.core.scans.window import Box
from verso.ru.scans.zoom import COLUMNS, DEFAULT_TOP, column_window, resolve, row_band


class TestColumnWindow:
    def test_named_column_of_a_part(self):
        assert column_window(1, "godparents") == COLUMNS[1]["godparents"]

    def test_no_column_is_the_whole_width(self):
        assert column_window(1, None) == (0.0, 1.0)
        assert column_window(None, None) == (0.0, 1.0)

    def test_column_without_part_is_refused(self):
        # The same word means a different window in ч.1 and ч.3, so guessing a
        # part would silently crop the wrong columns.
        with pytest.raises(ValueError, match="needs --part"):
            column_window(None, "count")

    def test_unknown_column_lists_the_known_ones(self):
        with pytest.raises(ValueError, match="godparents"):
            column_window(1, "sureties")   # ч.2's column, not ч.1's

    @pytest.mark.parametrize("part", sorted(COLUMNS))
    def test_every_preset_is_a_valid_window(self, part):
        for name, (x0, x1) in COLUMNS[part].items():
            assert 0.0 <= x0 < x1 <= 1.0, f"ч.{part} {name}"

    def test_columns_overlap_rather_than_abut(self):
        # A scribe's column boundary wanders between leaves; an overlap costs
        # nothing and a name cut in half by an exact boundary costs a re-crop.
        parents = COLUMNS[1]["parents"]
        godparents = COLUMNS[1]["godparents"]
        assert godparents[0] < parents[1], "ч.1 parents/godparents must overlap"


class TestRowBand:
    def test_rows_partition_the_writing_area(self):
        first = row_band(1, 4, pad=0.0)
        last = row_band(4, 4, pad=0.0)
        assert first[0] == pytest.approx(DEFAULT_TOP)
        assert last[1] == pytest.approx(1.0)

    def test_consecutive_rows_meet(self):
        assert row_band(2, 5, pad=0.0)[1] == pytest.approx(row_band(3, 5, pad=0.0)[0])

    def test_pad_widens_both_sides_and_clamps(self):
        y0, y1 = row_band(1, 3, pad=0.5)
        assert (y0, y1) == (0.0, min(1.0, y1))
        assert y1 <= 1.0

    def test_single_row_is_the_whole_writing_area(self):
        assert row_band(1, 1, pad=0.0) == (DEFAULT_TOP, 1.0)

    @pytest.mark.parametrize("row,of", [(0, 3), (4, 3), (-1, 3)])
    def test_row_outside_the_page_is_refused(self, row, of):
        with pytest.raises(ValueError, match="within"):
            row_band(row, of)

    def test_zero_rows_is_refused(self):
        with pytest.raises(ValueError, match="M ≥ 1"):
            row_band(1, 0)


class TestResolve:
    def test_column_and_row_combine(self):
        box = resolve(part=3, column="age", row=(2, 4), pad=0.0)
        assert (box.x0, box.x1) == COLUMNS[3]["age"]
        assert (box.y0, box.y1) == row_band(2, 4, pad=0.0)

    def test_no_row_is_the_whole_writing_area(self):
        box = resolve(part=1, column="parents")
        assert (box.y0, box.y1) == (DEFAULT_TOP, 1.0)

    def test_box_overrides_everything(self):
        box = resolve(part=1, column="parents", row=(1, 5), box=(0.1, 0.2, 0.3, 0.4))
        assert box == Box(0.1, 0.2, 0.3, 0.4)

    def test_box_wants_fractions_not_pixels(self):
        # The mistake this catches is real: a leaf is ~950 px across, and typing
        # pixel coordinates would silently crop the top-left corner.
        with pytest.raises(ValueError, match="FRACTIONS"):
            resolve(box=(100.0, 200.0, 400.0, 600.0))

    def test_box_wants_x0_y0_x1_y1_in_order(self):
        with pytest.raises(ValueError, match="x0<x1"):
            resolve(box=(0.6, 0.2, 0.3, 0.4))

    def test_pixels_scale_to_the_frame(self):
        assert Box(0.0, 0.5, 0.5, 1.0).pixels(1000, 2000) == (0, 1000, 500, 2000)


class TestTheBoxItReadsInPractice:
    """The windows that actually settled a reading, kept as a regression."""

    def test_godparents_column_covers_the_hand_cut_window(self):
        # Which of two spellings a godparent's surname was got settled at 8× on
        # x 0.55–0.99 of a leaf; the preset must contain that window.
        x0, x1 = COLUMNS[1]["godparents"]
        assert x0 <= 0.55 and x1 >= 0.99

    def test_parents_column_covers_the_hand_cut_window(self):
        # A parents' column cut by hand, at x 0.28–0.66.
        x0, x1 = COLUMNS[1]["parents"]
        assert x0 <= 0.28 and x1 >= 0.66

    def test_part3_age_column_is_separable_from_the_name(self):
        # An age is the only thing a burial gives towards a birth date, and it
        # is read on its own — «1 мѣс.» vs «1 нед.» can decide a birth year.
        name = COLUMNS[3]["deceased"]
        age = COLUMNS[3]["age"]
        assert age[1] > name[1]
