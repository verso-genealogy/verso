"""verso.core.scans.stanza — an album's geometry read from its `scans.toml`, which the scan tools never write."""
from __future__ import annotations

import json
from pathlib import Path

from verso.core.scans import stanza
from verso.core.scans.stanza import Stanza, enhance_for, for_album, parse, rotation


def test_a_frame_declares_its_own_rotation(tmp_path: Path):
    (tmp_path / "scans.toml").write_text(
        '[album."Маниловка 1900 (999-1-3)"]\nrotate = 90\nrotate_frames = { "кадр1" = 0 }\n', encoding="utf-8")
    turn = rotation(tmp_path)
    assert turn("кадр1") == 0
    assert turn("кадр2") == 90


def test_no_stanza_is_no_rotation(tmp_path: Path):
    assert rotation(tmp_path)("кадр1") == 0


def test_zoom_takes_the_albums_enhance_from_the_village_file(tmp_path: Path):
    # Verso's «Бледные чернила» writes `enhance` into the village's stanza; the export's own copy shadows that file,
    # so the durable one is asked too.
    album_dir, village = tmp_path / "cache" / "Маниловка 1882", tmp_path / "Маниловка"
    album_dir.mkdir(parents=True)
    village.mkdir()
    (album_dir / "scans.toml").write_text(
        f'[album."Маниловка 1882"]\nframes = "side"\nvillage = {json.dumps(str(village), ensure_ascii=False)}\n',
        encoding="utf-8")
    (village / "scans.toml").write_text('[album."Маниловка 1882"]\nenhance = 1.7\n', encoding="utf-8")

    def enhance() -> float:
        path, title, stanzas = for_album(album_dir)
        return enhance_for(album_dir, layout=None, village=None, read_path=path, title=title,
                           album=stanzas.album(title) if title else None)

    assert enhance() == 1.7
    # The album's own copy, when it says so, is asked first; no stanza is plain.
    (album_dir / "scans.toml").write_text('[album."Маниловка 1882"]\nenhance = 1.6\n', encoding="utf-8")
    assert enhance() == 1.6
    assert enhance_for(album_dir, layout=None, village=None, read_path=None, title=None, album=None) == 1.0


def test_the_keys_the_tools_cut_by_are_read_and_the_rest_passed_over():
    text = ('[album."Маниловка 1900"]\nframes = "spread"\ntop = 0.2\nbottom = 0.9\nrotate = -90\n'
            'rotate_frames = { "12об" = 450 }\nenhance = 1.6\nvillage = "../village"\nnote = "a note"\n'
            'source = "dir"\nsource_id = "x"\ngrey = true\n'
            '[[album."Маниловка 1900".box]]\nfolio = "12об"\npart = 1\nrecord = 3\nbox = [0.1, 0.2, 0.3, 0.4]\n')
    assert parse(text).albums == {"Маниловка 1900": Stanza(
        title="Маниловка 1900", frames="spread", top=0.2, bottom=0.9, rotate=270, rotate_frames=(("12об", 90),),
        enhance=1.6, village="../village")}


def test_an_enhance_out_of_range_or_beside_an_ink_is_plain():
    for body in ("enhance = 9", "enhance = true", 'enhance = "1.5"', 'enhance = 1.6\nink = "tone"'):
        assert parse(f'[album."a"]\n{body}\n').albums["a"].enhance == 1.0
    assert parse('[album."a"]\nenhance = 1.6\nink = "violet"\n').albums["a"].enhance == 1.6


def test_an_album_is_named_by_its_title_or_a_part_of_it(tmp_path: Path):
    (tmp_path / "scans.toml").write_text('[album."Маниловка 1900"]\ntop = 0.1\n[album."Маниловка 1901"]\ntop = 0.2\n',
                                         encoding="utf-8")
    assert for_album(tmp_path)[1] is None                       # two albums, none named
    assert for_album(tmp_path, album_title="1901")[1] == "Маниловка 1901"
    assert for_album(tmp_path, album_title="Маниловка")[1] == "Маниловка"    # two contain it: as given
    _, title, stanzas = for_album(tmp_path, album_title="1900")
    assert title is not None and stanzas.album(title) == Stanza(title="Маниловка 1900", top=0.1)


def test_the_albums_own_file_wins_over_the_villages(tmp_path: Path):
    album, village = tmp_path / "album", tmp_path / "village"
    album.mkdir()
    village.mkdir()
    (village / "scans.toml").write_text('[album."a"]\nrotate = 90\n', encoding="utf-8")
    assert stanza.find_file(album, village) == village / "scans.toml"
    assert rotation(album, village=str(village))("1") == 90
    (album / "scans.toml").write_text('[album."a"]\nrotate = 180\n', encoding="utf-8")
    assert stanza.find_file(album, village) == album / "scans.toml"
    assert rotation(album, village=str(village))("1") == 180
    assert rotation(album, layout=str(village / "scans.toml"))("1") == 90


def test_the_durable_file_is_named_before_the_one_read(tmp_path: Path):
    read = tmp_path / "album" / "scans.toml"
    kw = {"album_dir": tmp_path / "album", "read_path": read}
    assert stanza.durable_file(layout="x.toml", village="v", album_village="w", **kw) == Path("x.toml")
    assert stanza.durable_file(layout=None, village="v", album_village="w", **kw) == Path("v") / "scans.toml"
    assert stanza.durable_file(layout=None, village=None, album_village="w", **kw) == Path("w") / "scans.toml"
    assert stanza.durable_file(layout=None, village=None, album_village="", **kw) == read
    assert stanza.durable_file(layout=None, village=None, album_village="", album_dir=tmp_path,
                               read_path=None) == tmp_path / "scans.toml"


def test_a_file_that_is_no_toml_is_refused_not_guessed(tmp_path):
    """A broken `scans.toml` is no album: StanzaError names the file and where the TOML broke."""
    import pytest
    (tmp_path / "scans.toml").write_text('[album."Маниловка 1902"\nframes = "spread"\n', encoding="utf-8")
    with pytest.raises(stanza.StanzaError, match=r"scans\.toml is not TOML.*line 1"):
        stanza.for_album(tmp_path)
