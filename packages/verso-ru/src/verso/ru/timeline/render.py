"""Layout → one self-contained HTML page.

No build step, no CDN beyond the webfont (which degrades to a system stack), no
external data: the page is a single file you can open from disk or publish
as-is. Pure — it takes a `Timeline` and its `Layout` and returns a string — so
the CLI stays the only thing that touches a filesystem.

The visual language is that of the project's own design sketch, carried over
deliberately: a nebula ground, a seeded starfield, threads doubled as a blurred
glow under a crisp stroke, and a turbulence displacement that makes the whole
field breathe.
What changed is that every mark now answers to a record — see `projection` for
the rules a hollow node or a fading thread stands for.
"""
from __future__ import annotations

import html
import json
from collections.abc import Iterable

from verso.ru.timeline.layout import (
    NODE_BIRTH, NODE_DEATH, NODE_LAST_SEEN, NODE_MARRIAGE, Layout, Thread)
from verso.ru.timeline.model import HUE_LINE_A, HUE_LINE_B, HUE_UNATTACHED, Timeline

# Two palettes, as the sketch offered. The keys are the model's hue slots:
# one blood line each, plus the third for people the records leave unattached.
PALETTES: dict[str, dict[str, str]] = {
    "Неон": {HUE_LINE_A: "#a78bfa", HUE_LINE_B: "#22d3ee", HUE_UNATTACHED: "#f472b6"},
    "Лёд": {HUE_LINE_A: "#7dd3fc", HUE_LINE_B: "#5eead4", HUE_UNATTACHED: "#c4b5fd"},
}
DEFAULT_PALETTE = "Неон"

# Per-band spectra for the «Спектр» style, from the sketch.
SPECTRA: tuple[tuple[str, str, str], ...] = (
    ("#a78bfa", "#7dd3fc", "#22d3ee"),
    ("#f472b6", "#fb7185", "#fbbf24"),
    ("#22d3ee", "#5eead4", "#a3e635"),
    ("#c4b5fd", "#f0abfc", "#f472b6"),
    ("#34d399", "#22d3ee", "#818cf8"),
    ("#fbbf24", "#f472b6", "#a78bfa"),
)

STAR_SEED = 20260818


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _stars(width: float, height: float, count: int, big: int) -> tuple[list[str], list[str]]:
    """The sketch's starfield, LCG and all, so the sky is identical run to run
    and no `random` call can leak nondeterminism into a committed file."""
    seed = STAR_SEED

    def rnd() -> float:
        nonlocal seed
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        return seed / 0x7FFFFFFF

    tints = ("#e9e9ed", "#c4b5fd", "#a5f3fc", "#e9e9ed", "#f5d0fe")
    small: list[str] = []
    for _ in range(count):
        x, y = rnd() * width, rnd() * height
        r, opacity = 0.7 + rnd() * 1.9, 0.12 + rnd() * 0.5
        tint = tints[int(rnd() * len(tints))]
        small.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{tint}" '
            f'opacity="{opacity:.2f}"/>'
        )
    bright: list[str] = []
    for _ in range(big):
        x, y = rnd() * width, rnd() * height
        r, opacity = 2.2 + rnd() * 1.6, 0.35 + rnd() * 0.35
        bright.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#e9e9ed" '
            f'opacity="{opacity:.2f}" filter="url(#gl)"/>'
        )
    return small, bright


def _defs(layout: Layout) -> str:
    """Filters, masks and the per-thread end-fade gradients.

    A thread with no recorded death has to fade at *its own* end, not at the
    canvas edge as the sketch did, so each such thread gets a userSpaceOnUse
    gradient over its final 90px. The stop colour is a CSS variable, which is
    what lets the palette switch at runtime.
    """
    parts: list[str] = [
        '<filter id="gl" x="-25%" y="-25%" width="150%" height="150%">'
        '<feGaussianBlur id="glblur" stdDeviation="7" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="b"/></feMerge></filter>',
        f'<filter id="wave" filterUnits="userSpaceOnUse" x="0" y="0" '
        f'width="{layout.width:.0f}" height="{layout.height:.0f}">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.0022 0.0055" numOctaves="2" '
        'seed="7" result="t">'
        '<animate attributeName="baseFrequency" dur="19s" repeatCount="indefinite" '
        'values="0.0022 0.0055;0.0031 0.0042;0.0018 0.0062;0.0022 0.0055"/></feTurbulence>'
        '<feDisplacementMap in="SourceGraphic" in2="t" xChannelSelector="R" '
        'yChannelSelector="G" scale="9">'
        '<animate attributeName="scale" dur="11s" repeatCount="indefinite" '
        'values="6;12;6"/></feDisplacementMap></filter>',
        f'<filter id="aurora" filterUnits="userSpaceOnUse" x="-200" y="-100" '
        f'width="{layout.width + 400:.0f}" height="{layout.height + 200:.0f}">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.011 0.004" numOctaves="3" '
        'seed="11" result="at">'
        '<animate attributeName="baseFrequency" dur="23s" repeatCount="indefinite" '
        'values="0.011 0.004;0.008 0.006;0.014 0.003;0.011 0.004"/></feTurbulence>'
        '<feDisplacementMap in="SourceGraphic" in2="at" xChannelSelector="G" '
        'yChannelSelector="R" scale="46" result="ad">'
        '<animate attributeName="scale" dur="15s" repeatCount="indefinite" '
        'values="28;62;28"/></feDisplacementMap>'
        '<feGaussianBlur in="ad" stdDeviation="7"/></filter>',
        '<filter id="neb" x="-60%" y="-30%" width="220%" height="160%">'
        '<feGaussianBlur stdDeviation="46"/></filter>',
        f'<linearGradient id="vfadeg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#000"/><stop offset="0.12" stop-color="#fff"/>'
        f'<stop offset="0.88" stop-color="#fff"/><stop offset="1" stop-color="#000"/>'
        f'</linearGradient>'
        f'<mask id="vfade"><rect x="0" y="0" width="{layout.width:.0f}" '
        f'height="{layout.height:.0f}" fill="url(#vfadeg)"/></mask>',
    ]
    for index, spectrum in enumerate(SPECTRA):
        g1, g2, g3 = spectrum
        parts.append(
            f'<linearGradient id="spec-{index}" x1="0" y1="0" x2="1" y2="0">'
            f'<stop offset="0" stop-color="{g1}" stop-opacity="0"/>'
            f'<stop offset="0.2" stop-color="{g1}"/>'
            f'<stop offset="0.5" stop-color="{g2}"/>'
            f'<stop offset="0.8" stop-color="{g3}"/>'
            f'<stop offset="1" stop-color="{g3}" stop-opacity="0"/></linearGradient>'
        )
    for thread in layout.threads:
        stops = _fade_stops(thread)
        if stops is None:
            continue
        colour = f"stop-color:var(--hue-{thread.hue})"
        body = "".join(
            f'<stop offset="{offset:.4f}" style="{colour}" stop-opacity="{opacity}"/>'
            for offset, opacity in stops
        )
        parts.append(
            f'<linearGradient id="fade-{_e(thread.res_name)}" gradientUnits="userSpaceOnUse" '
            f'x1="{thread.start_x:.1f}" y1="0" x2="{thread.end_x:.1f}" y2="0">'
            f"{body}</linearGradient>"
        )
    return "<defs>" + "".join(parts) + "</defs>"


def _fade_stops(thread: Thread) -> list[tuple[float, str]] | None:
    """Gradient stops for a thread that is uncertain at one or both ends, or None
    when the records pin both ends down and a flat stroke is the honest one.

    The stroke is opaque exactly where the evidence is: it ramps up across a
    birth window and down past the last sighting.
    """
    span = thread.end_x - thread.start_x
    if span <= 0:
        return None
    stops: list[tuple[float, str]] = []
    if thread.fade_in_to is not None and thread.fade_in_to > thread.start_x:
        stops.append((0.0, "0"))
        stops.append((min((thread.fade_in_to - thread.start_x) / span, 1.0), "1"))
    else:
        stops.append((0.0, "1"))
    if thread.fade_out_from is not None and thread.fade_out_from < thread.end_x:
        stops.append((max((thread.fade_out_from - thread.start_x) / span, 0.0), "1"))
        stops.append((1.0, "0"))
    else:
        stops.append((1.0, "1"))
    # A flat 1→1 pair carries no information; leave the stroke plain.
    if all(opacity == "1" for _, opacity in stops):
        return None
    return stops


def _bands_svg(layout: Layout) -> str:
    """Eras as wide grounds, events in the three switchable styles."""
    eras: list[str] = []
    for band in layout.bands:
        if not band.is_era:
            continue
        eras.append(
            f'<g class="hit band-hit" data-title="{_e(band.label)}" '
            f'data-year="{_e(band.years)}" data-detail="{_e(band.detail)}">'
            f'<rect class="era-fill era-{band.index % 2}" x="{band.x:.1f}" y="0" '
            f'width="{band.width:.1f}" '
            f'height="{layout.height:.0f}" mask="url(#vfade)"/>'
            f'<line class="era-edge" x1="{band.x:.1f}" y1="0" x2="{band.x:.1f}" '
            f'y2="{layout.height:.0f}"/>'
            f'<text class="era-label" x="{band.label_x:.1f}" y="{band.label_y:.1f}">'
            f'{_e(band.label)}</text></g>'
        )

    nebula: list[str] = []
    spectrum: list[str] = []
    lines: list[str] = []
    for band in layout.bands:
        if band.is_era:
            continue
        spec = SPECTRA[band.index % len(SPECTRA)]
        centre = band.x + band.width / 2
        rx = max(band.width / 2 + 46.0, 58.0)
        nebula.append(
            f'<ellipse cx="{centre:.1f}" cy="{layout.height / 2:.0f}" rx="{rx:.1f}" '
            f'ry="{layout.height * 0.46:.0f}" fill="{spec[0]}" opacity="0.13" '
            f'filter="url(#neb)"/>'
        )
        spectrum.append(
            f'<rect x="{band.x:.1f}" y="0" width="{max(band.width, 30.0):.1f}" '
            f'height="{layout.height:.0f}" fill="url(#spec-{band.index % len(SPECTRA)})" '
            f'mask="url(#vfade)" opacity="0.22" filter="url(#aurora)"/>'
        )
        lines.append(
            f'<rect x="{band.x:.1f}" y="0" width="{band.width:.1f}" '
            f'height="{layout.height:.0f}" fill="#9aa0c9" opacity="0.06"/>'
        )
        for style_group in (nebula, spectrum, lines):
            style_group.append(
                f'<line class="ev-edge" x1="{band.x:.1f}" y1="0" x2="{band.x:.1f}" '
                f'y2="{layout.height:.0f}"/>'
            )

    hits: list[str] = []
    for band in layout.bands:
        if band.is_era:
            continue
        hits.append(
            f'<g class="hit band-hit" data-title="{_e(band.label)}" '
            f'data-year="{_e(band.years)}" data-detail="{_e(band.detail)}">'
            f'<rect x="{band.x - 8:.1f}" y="0" width="{band.width + 16:.1f}" '
            f'height="{layout.height:.0f}" fill="transparent"/>'
            f'<text class="ev-label" x="{band.label_x:.1f}" y="{band.label_y:.1f}">'
            f'{_e(band.label)}</text></g>'
        )

    return (
        f'<g id="eras">{"".join(eras)}</g>'
        f'<g id="ev-neb" class="ev-style">{"".join(nebula)}</g>'
        f'<g id="ev-spec" class="ev-style" hidden>{"".join(spectrum)}</g>'
        f'<g id="ev-lines" class="ev-style" hidden>{"".join(lines)}</g>'
        f'<g id="ev-hits">{"".join(hits)}</g>'
    )


def _groups_svg(layout: Layout) -> str:
    out: list[str] = []
    for group in layout.groups:
        subtitle = f"{group.count} чел."
        out.append(
            f'<g class="grp">'
            f'<line class="grp-rule" x1="0" y1="{group.y + 42:.1f}" '
            f'x2="{layout.width:.0f}" y2="{group.y + 42:.1f}"/>'
            f'<text class="grp-label hue-{group.hue}" x="14" y="{group.y + 34:.1f}">'
            f'{_e(group.label)}</text>'
            f'<text class="grp-count" x="14" y="{group.y + 60:.1f}">{_e(subtitle)}</text>'
            f'</g>'
        )
    return f'<g id="groups">{"".join(out)}</g>'


def _threads_svg(layout: Layout) -> str:
    glow: list[str] = []
    crisp: list[str] = []
    for thread in layout.threads:
        if not thread.d:
            continue
        stroke = (
            f' stroke="url(#fade-{_e(thread.res_name)})"'
            if _fade_stops(thread) is not None else ""
        )
        glow.append(
            f'<path class="t hue-{thread.hue}" d="{thread.d}"{stroke} stroke-width="6" '
            f'opacity="0.4"/>'
        )
        crisp.append(f'<path class="t hue-{thread.hue}" d="{thread.d}"{stroke}/>')
    return (
        f'<g id="threads">'
        f'<g id="thread-glow" filter="url(#gl)">{"".join(glow)}</g>'
        f'<g id="thread-line">{"".join(crisp)}</g></g>'
    )


def _nodes_svg(layout: Layout) -> str:
    out: list[str] = []
    for node in layout.nodes:
        hollow = " hollow" if node.hollow else ""
        rings = ""
        if node.kind == NODE_MARRIAGE:
            rings = (
                f'<circle class="ring hue-{node.hue}{hollow}" cx="{node.x:.1f}" '
                f'cy="{node.y:.1f}" r="15"/>'
            )
        radius = {NODE_BIRTH: 5.5, NODE_DEATH: 6.0, NODE_MARRIAGE: 7.5,
                  NODE_LAST_SEEN: 3.4}[node.kind]
        kind_class = {
            NODE_BIRTH: "n-birth", NODE_DEATH: "n-death", NODE_MARRIAGE: "n-mar",
            NODE_LAST_SEEN: "n-last",
        }[node.kind]
        out.append(
            f'<g class="hit node" data-title="{_e(node.title)}" data-year="{_e(node.year)}" '
            f'data-detail="{_e(node.detail)}" data-hue="{node.hue}">'
            f'<circle class="halo hue-{node.hue}" cx="{node.x:.1f}" cy="{node.y:.1f}" '
            f'r="{radius + 5:.1f}" filter="url(#gl)"/>'
            f'{rings}'
            f'<circle class="{kind_class} hue-{node.hue}{hollow}" cx="{node.x:.1f}" '
            f'cy="{node.y:.1f}" r="{radius}"/>'
            f'<circle class="grab" cx="{node.x:.1f}" cy="{node.y:.1f}" r="16"/>'
            f'</g>'
        )
    return f'<g id="nodes">{"".join(out)}</g>'


def _labels_svg(layout: Layout) -> str:
    out = [
        f'<text class="lab hue-{label.hue}" x="{label.x:.1f}" y="{label.y:.1f}">'
        f'{_e(label.text)}</text>'
        for label in layout.labels
    ]
    return f'<g id="labels">{"".join(out)}</g>'


def _decades_svg(layout: Layout) -> str:
    grid = [
        f'<line class="dec" x1="{d.x:.1f}" y1="0" x2="{d.x:.1f}" y2="{layout.height:.0f}"/>'
        for d in layout.decades
    ]
    text = [
        f'<text class="dec-lab" x="{d.x:.1f}" y="{layout.height - 44:.1f}">{_e(d.label)}</text>'
        for d in layout.decades
    ]
    return f'<g id="decades">{"".join(grid)}{"".join(text)}</g>'


def _notes_html(notes: Iterable[str]) -> str:
    items = "".join(f"<li>{_e(note)}</li>" for note in notes)
    return f"<ul class='notes'>{items}</ul>" if items else ""


def render(timeline: Timeline, layout: Layout) -> str:
    """The whole page as one string."""
    palette = PALETTES[DEFAULT_PALETTE]
    small_stars, big_stars = _stars(layout.width, layout.height, 190, 9)
    people = len(timeline.people)
    marriages = len(timeline.marriages)
    joined = sum(1 for m in timeline.marriages.values() if m.joins_two_threads)
    palette_options = "".join(
        f'<option value="{_e(name)}"{" selected" if name == DEFAULT_PALETTE else ""}>'
        f"{_e(name)}</option>"
        for name in PALETTES
    )
    palette_json = json.dumps(
        {
            name: {
                "v": hues[HUE_LINE_A], "c": hues[HUE_LINE_B], "p": hues[HUE_UNATTACHED],
            }
            for name, hues in PALETTES.items()
        },
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(timeline.village)} — родословная лента</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap">
<style>
:root {{
  --bg: #161826; --surface: #1b1d2e; --text: #e9e9ed; --muted: #a2a6c4;
  --dim: #8e93b8; --divider: rgba(233,233,237,0.16);
  --font: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif;
  --hue-v: {palette[HUE_LINE_A]}; --hue-c: {palette[HUE_LINE_B]}; --hue-p: {palette[HUE_UNATTACHED]};
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; height: 100%; background: var(--bg); color: var(--text);
  font-family: var(--font); overflow: hidden; }}
.stage {{ position: fixed; inset: 0; overflow: hidden;
  background:
    radial-gradient(900px 620px at 16% 12%, rgba(145,132,217,.20), rgba(145,132,217,0) 70%),
    radial-gradient(1100px 700px at 82% 78%, rgba(34,211,238,.13), rgba(34,211,238,0) 72%),
    radial-gradient(700px 500px at 58% 42%, rgba(244,114,182,.09), rgba(244,114,182,0) 70%),
    radial-gradient(1400px 900px at 30% 30%, #1b1d31 0%, #141624 55%, #0d0e18 100%); }}
.aurora {{ position: absolute; inset: -10%;
  background: conic-gradient(from 210deg at 62% 58%, rgba(145,132,217,.10),
    rgba(34,211,238,.06), rgba(13,14,24,0) 55%, rgba(145,132,217,.08));
  filter: blur(60px); opacity: .7; pointer-events: none; }}
svg {{ position: absolute; inset: 0; width: 100%; height: 100%; display: block;
  cursor: grab; touch-action: none; }}
svg.dragging {{ cursor: grabbing; }}

.t {{ fill: none; stroke-width: 1.5; stroke-linecap: round; }}
.t.hue-v {{ stroke: var(--hue-v); }} .t.hue-c {{ stroke: var(--hue-c); }}
.t.hue-p {{ stroke: var(--hue-p); }}
.n-birth.hue-v, .n-mar.hue-v {{ fill: var(--hue-v); }}
.n-birth.hue-c, .n-mar.hue-c {{ fill: var(--hue-c); }}
.n-birth.hue-p, .n-mar.hue-p {{ fill: var(--hue-p); }}
.n-birth.hollow, .n-mar.hollow {{ fill: var(--surface); stroke-width: 2; stroke-dasharray: 3 2.4; }}
.n-birth.hollow.hue-v, .n-mar.hollow.hue-v {{ stroke: var(--hue-v); }}
.n-birth.hollow.hue-c, .n-mar.hollow.hue-c {{ stroke: var(--hue-c); }}
.n-birth.hollow.hue-p, .n-mar.hollow.hue-p {{ stroke: var(--hue-p); }}
.n-death {{ fill: none; stroke-width: 2.4; }}
.n-last {{ fill: none; stroke-width: 1.4; opacity: .5; }}
.n-last.hue-v {{ stroke: var(--hue-v); }} .n-last.hue-c {{ stroke: var(--hue-c); }}
.n-last.hue-p {{ stroke: var(--hue-p); }}
.n-death.hue-v {{ stroke: var(--hue-v); }} .n-death.hue-c {{ stroke: var(--hue-c); }}
.n-death.hue-p {{ stroke: var(--hue-p); }}
.ring {{ fill: none; stroke-width: 1.3; opacity: .5; }}
.ring.hue-v {{ stroke: var(--hue-v); }} .ring.hue-c {{ stroke: var(--hue-c); }}
.ring.hue-p {{ stroke: var(--hue-p); }}
.ring.hollow {{ stroke-dasharray: 3 4; }}
.halo {{ opacity: .22; transition: opacity .18s; }}
.halo.hue-v {{ fill: var(--hue-v); }} .halo.hue-c {{ fill: var(--hue-c); }}
.halo.hue-p {{ fill: var(--hue-p); }}
.grab {{ fill: transparent; }}
.node {{ cursor: pointer; }}
.node:hover .halo {{ opacity: .75; }}

.lab {{ font-size: 13px; letter-spacing: .2px; opacity: .82; }}
.lab.hue-v {{ fill: var(--hue-v); }} .lab.hue-c {{ fill: var(--hue-c); }}
.lab.hue-p {{ fill: var(--hue-p); }}
#labels.off {{ display: none; }}

.dec {{ stroke: #9aa0c9; stroke-width: 1; opacity: .06; }}
.dec-lab {{ fill: var(--dim); font-size: 15px; letter-spacing: 2px; opacity: .5;
  text-anchor: middle; }}
.grp-rule {{ stroke: var(--divider); stroke-width: 1; opacity: .5; }}
.grp-label {{ font-size: 19px; font-weight: 500; letter-spacing: 1.4px;
  text-transform: uppercase; opacity: .9; }}
.grp-label.hue-v {{ fill: var(--hue-v); }} .grp-label.hue-c {{ fill: var(--hue-c); }}
.grp-label.hue-p {{ fill: var(--hue-p); }}
.grp-count {{ fill: var(--dim); font-size: 13px; letter-spacing: 1px; opacity: .7; }}

.era-fill {{ fill: #9aa0c9; }}
.era-0 {{ opacity: .075; }}
.era-1 {{ opacity: .022; }}
.era-edge {{ stroke: #b7add9; stroke-width: 1; opacity: .2; stroke-dasharray: 2 8; }}
.era-label {{ fill: #b7add9; font-size: 15px; letter-spacing: 1.6px; opacity: .55;
  text-transform: uppercase; }}
.ev-edge {{ stroke: #b7add9; stroke-width: 1; opacity: .22; stroke-dasharray: 2 8; }}
.ev-label {{ fill: #cfd3e5; font-size: 13.5px; letter-spacing: 1.2px; opacity: .62; }}
.band-hit {{ cursor: help; }}
.band-hit:hover .ev-label, .band-hit:hover .era-label {{ opacity: 1; }}
#bands.off {{ display: none; }}

.panel {{ position: fixed; z-index: 5; background: rgba(27,29,46,.82);
  backdrop-filter: blur(9px); border: 1px solid var(--divider); border-radius: 12px; }}
.top {{ top: 18px; left: 18px; padding: 15px 19px 16px; max-width: 430px; }}
.top h1 {{ margin: 0; font-size: 21px; font-weight: 500; letter-spacing: .1px; }}
.top .sub {{ margin-top: 5px; font-size: 13px; color: var(--muted); }}
.notes {{ margin: 11px 0 0; padding-left: 17px; font-size: 12px; line-height: 1.5;
  color: var(--muted); }}
.notes li {{ margin-bottom: 5px; }}
.top details summary {{ cursor: pointer; font-size: 12px; color: var(--dim);
  margin-top: 10px; user-select: none; }}

.controls {{ top: 18px; right: 18px; padding: 13px 15px; display: grid; gap: 9px;
  font-size: 12.5px; color: var(--muted); }}
.controls label {{ display: flex; align-items: center; gap: 8px; justify-content: space-between; }}
.controls select, .controls input[type=range] {{ font: inherit; font-size: 12px; }}
.controls select {{ background: var(--surface); color: var(--text);
  border: 1px solid var(--divider); border-radius: 6px; padding: 3px 6px; }}
.controls button {{ font: inherit; font-size: 12px; color: var(--text);
  background: transparent; border: 1px solid var(--divider); border-radius: 6px;
  padding: 5px 9px; cursor: pointer; }}
.controls button:hover {{ background: rgba(233,233,237,.07); }}

.legend {{ left: 18px; bottom: 18px; padding: 11px 15px; display: flex; gap: 17px;
  font-size: 12px; color: var(--muted); align-items: center; flex-wrap: wrap; }}
.legend i {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%;
  margin-right: 6px; vertical-align: -1px; background: var(--muted); }}
.legend .hollow {{ background: transparent; border: 2px dashed var(--muted); }}
.legend .ring {{ background: transparent; border: 2px solid var(--muted); }}

#tip {{ position: fixed; z-index: 9; pointer-events: none; opacity: 0;
  transition: opacity .12s; background: var(--surface); border: 1px solid var(--divider);
  border-left: 3px solid var(--tip-accent, var(--hue-v)); border-radius: 10px;
  padding: 11px 16px 13px;
  box-shadow: 0 10px 30px rgba(0,0,0,.5); max-width: 340px; }}
#tip.on {{ opacity: 1; }}
#tip .tt {{ font-size: 15px; color: var(--text); }}
#tip .ty {{ font-size: 12.5px; letter-spacing: 1.6px; margin-top: 5px;
  color: var(--tip-accent, var(--hue-v)); }}
#tip .td {{ font-size: 12.5px; line-height: 1.35; color: var(--muted); margin-top: 6px; }}
@media (max-width: 900px) {{ .top {{ max-width: 62vw; }} .controls {{ display: none; }} }}
</style>
</head>
<body>
<div class="stage">
  <div class="aurora"></div>
  <svg id="sky" viewBox="0 0 {layout.width:.0f} {layout.height:.0f}"
       preserveAspectRatio="xMidYMid meet">
    {_defs(layout)}
    <g id="cam">
      <g id="stars">{"".join(small_stars)}{"".join(big_stars)}</g>
      <g id="bands">{_bands_svg(layout)}</g>
      {_decades_svg(layout)}
      {_groups_svg(layout)}
      <g id="wavy" filter="url(#wave)">
        {_threads_svg(layout)}
        {_nodes_svg(layout)}
      </g>
      {_labels_svg(layout)}
    </g>
  </svg>
</div>

<div class="panel top">
  <h1>{_e(timeline.village)} — родословная лента</h1>
  <div class="sub">{people} человек, {marriages} браков ({joined} — между своими),
    {timeline.first_year}–{timeline.last_year}</div>
  <details>
    <summary>Чего лента не показывает</summary>
    {_notes_html(timeline.notes)}
  </details>
</div>

<div class="panel controls">
  <label>Палитра <select id="c-pal">{palette_options}</select></label>
  <label>История <select id="c-hist">
    <option value="neb">Туманность</option>
    <option value="spec">Спектр</option>
    <option value="lines">Линии</option>
  </select></label>
  <label>Имена <input type="checkbox" id="c-names" checked></label>
  <label>Колыхание <input type="checkbox" id="c-wave" checked></label>
  <label>Фон-эпохи <input type="checkbox" id="c-bands" checked></label>
  <label>Свечение <input type="range" id="c-glow" min="0" max="16" step="1" value="7"></label>
  <button id="c-reset">Сбросить вид</button>
</div>

<div class="panel legend">
  <span><i></i>рождение</span>
  <span><i class="hollow"></i>дата расчётная</span>
  <span><i class="ring"></i>смерть записана</span>
  <span>линия угасает — даты смерти нет, только «жив в таком-то году»</span>
  <span>линия проявляется — год рождения известен лишь промежутком</span>
  <span>колесо — масштаб, перетаскивание — сдвиг</span>
</div>

<div id="tip"><div class="tt"></div><div class="ty"></div><div class="td"></div></div>

<script>
(function () {{
  var PALETTES = {palette_json};
  var svg = document.getElementById('sky');
  var cam = document.getElementById('cam');
  var tip = document.getElementById('tip');
  var view = {{ x: 0, y: 0, k: 1 }};

  function apply() {{
    cam.setAttribute('transform',
      'translate(' + view.x.toFixed(2) + ',' + view.y.toFixed(2) + ') scale(' + view.k.toFixed(4) + ')');
  }}

  // Zoom about the pointer: the SVG point under the cursor must not move.
  svg.addEventListener('wheel', function (e) {{
    e.preventDefault();
    var rect = svg.getBoundingClientRect();
    var scale = svg.viewBox.baseVal.width / rect.width;
    var px = (e.clientX - rect.left) * scale, py = (e.clientY - rect.top) * scale;
    var k = Math.min(14, Math.max(0.6, view.k * Math.exp(-e.deltaY * 0.0014)));
    view.x = px - (px - view.x) * (k / view.k);
    view.y = py - (py - view.y) * (k / view.k);
    view.k = k;
    apply();
  }}, {{ passive: false }});

  var drag = null;
  svg.addEventListener('pointerdown', function (e) {{
    drag = {{ x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }};
    svg.classList.add('dragging');
    svg.setPointerCapture(e.pointerId);
  }});
  svg.addEventListener('pointermove', function (e) {{
    if (!drag) return;
    var rect = svg.getBoundingClientRect();
    var scale = svg.viewBox.baseVal.width / rect.width;
    view.x = drag.vx + (e.clientX - drag.x) * scale;
    view.y = drag.vy + (e.clientY - drag.y) * scale;
    apply();
  }});
  function endDrag(e) {{
    drag = null;
    svg.classList.remove('dragging');
    if (e && e.pointerId !== undefined && svg.hasPointerCapture(e.pointerId)) {{
      svg.releasePointerCapture(e.pointerId);
    }}
  }}
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);

  document.getElementById('c-reset').addEventListener('click', function () {{
    view = {{ x: 0, y: 0, k: 1 }};
    apply();
  }});

  // Tooltip. Anchored off the hovered element's screen box, so it follows the
  // camera without needing the transform maths again.
  var tt = tip.querySelector('.tt'), ty = tip.querySelector('.ty'), td = tip.querySelector('.td');
  document.querySelectorAll('.hit').forEach(function (el) {{
    el.addEventListener('pointerenter', function () {{
      if (drag) return;
      tt.textContent = el.dataset.title || '';
      ty.textContent = el.dataset.year || '';
      td.textContent = el.dataset.detail || '';
      td.style.display = el.dataset.detail ? '' : 'none';
      var hue = el.dataset.hue;
      tip.style.setProperty('--tip-accent',
        hue ? 'var(--hue-' + hue + ')' : 'var(--divider)');
      var box = el.getBoundingClientRect();
      tip.classList.add('on');
      var w = tip.offsetWidth, h = tip.offsetHeight;
      var left = Math.min(Math.max(box.left + box.width / 2 - w / 2, 12),
                          window.innerWidth - w - 12);
      var top = box.top - h - 14;
      if (top < 12) top = Math.min(box.bottom + 14, window.innerHeight - h - 12);
      tip.style.left = left + 'px';
      tip.style.top = top + 'px';
    }});
    el.addEventListener('pointerleave', function () {{ tip.classList.remove('on'); }});
  }});

  document.getElementById('c-pal').addEventListener('change', function (e) {{
    var p = PALETTES[e.target.value];
    if (!p) return;
    var root = document.documentElement.style;
    root.setProperty('--hue-v', p.v);
    root.setProperty('--hue-c', p.c);
    root.setProperty('--hue-p', p.p);
  }});
  document.getElementById('c-names').addEventListener('change', function (e) {{
    document.getElementById('labels').classList.toggle('off', !e.target.checked);
  }});
  document.getElementById('c-bands').addEventListener('change', function (e) {{
    document.getElementById('bands').classList.toggle('off', !e.target.checked);
  }});
  document.getElementById('c-wave').addEventListener('change', function (e) {{
    document.getElementById('wavy').setAttribute('filter',
      e.target.checked ? 'url(#wave)' : 'none');
  }});
  document.getElementById('c-glow').addEventListener('input', function (e) {{
    document.getElementById('glblur').setAttribute('stdDeviation', e.target.value);
  }});
  document.getElementById('c-hist').addEventListener('change', function (e) {{
    ['neb', 'spec', 'lines'].forEach(function (name) {{
      document.getElementById('ev-' + name).hidden = (name !== e.target.value);
    }});
  }});
}})();
</script>
</body>
</html>
"""
