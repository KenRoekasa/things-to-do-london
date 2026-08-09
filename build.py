#!/usr/bin/env python3
"""Build the London Field Guide pages.

    python3 build.py

Reads london-activities.md (the source of truth for venues) plus the shared
assets in build/, and writes three self-contained HTML files:

    index.html / london-guide.html   the guide
    events-2026.html                 the calendar

Everything is inlined — fonts, CSS, JS — so the pages work straight off the
filesystem with no network and no server.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"

SOURCE_MD = ROOT / "london-activities.md"
FONTS_CSS = BUILD / "fonts.css"
THEME_CSS = BUILD / "theme.css"
APP_JS = BUILD / "app.js"
EVENTS_MAIN = BUILD / "events-2026.main.html"

BUILT_ON = "9 Aug 2026"

ARROW = '<span class="arrow" aria-hidden="true">&#8599;</span>'

# Each category gets its own line colour and a short name for the filter pills.
LINES = [
    ("Competitive Socialising, Games & Sports", "Games & Sports", "line-1"),
    ("Entertainment & Immersive Experiences", "Entertainment", "line-2"),
    ("Bars, Rooftops & Dining", "Bars & Dining", "line-3"),
    ("Food To Try", "Food", "line-4"),
    ("Markets & Shopping", "Markets", "line-5"),
    ("Outdoors & General Activities", "Outdoors", "line-6"),
    ("Summer & Annual Festivals", "Festivals", "line-7"),
    ("Seasonal Events: Winter/Christmas", "Winter", "line-8"),
    ("Websites & Resources", "Resources", "line-9"),
]

MONTH_SEASON = {
    "m-jan": "winter", "m-feb": "winter", "m-mar": "spring",
    "m-apr": "spring", "m-may": "spring", "m-jun": "summer",
    "m-jul": "summer", "m-aug": "summer", "m-sep": "autumn",
    "m-oct": "autumn", "m-nov": "autumn", "m-dec": "winter",
}

MONTHS = [
    ("m-jan", "Jan"), ("m-feb", "Feb"), ("m-mar", "Mar"), ("m-apr", "Apr"),
    ("m-may", "May"), ("m-jun", "Jun"), ("m-jul", "Jul"), ("m-aug", "Aug"),
    ("m-sep", "Sep"), ("m-oct", "Oct"), ("m-nov", "Nov"), ("m-dec", "Dec"),
]

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


# --------------------------------------------------------------- parsing ----

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_links(value: str):
    """Split a markdown value into (name, url, trailing note) triples.

    Text sitting between links is treated as a note on the link before it, so
    '[Barbican](url) (timed tickets)' keeps its parenthetical.
    """
    items = []
    cursor = 0
    for match in LINK_RE.finditer(value):
        between = value[cursor:match.start()]
        note = between.strip().strip(",").strip()
        if note and items:
            items[-1]["note"] = note
        items.append({"name": match.group(1).strip(), "url": match.group(2).strip(), "note": ""})
        cursor = match.end()

    tail = value[cursor:].strip().strip(",").strip()
    if tail and items:
        items[-1]["note"] = (items[-1]["note"] + " " + tail).strip()
    return items


def parse_markdown(path: Path):
    """Return [{title, stops:[...]}] from the activities markdown."""
    sections = []
    current = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()

        if line.startswith("## "):
            # drop the leading emoji, keep the words
            title = re.sub(r"^##\s+", "", line)
            title = re.sub(r"^[^\w(]+\s*", "", title).strip()
            current = {"title": title, "stops": []}
            sections.append(current)
            continue

        if not line.startswith("- ") or current is None:
            continue

        item = line[2:].strip()
        bold = re.match(r"^\*\*(.+?)\*\*[:：]?\s*(.*)$", item)
        if not bold:
            continue

        head, rest = bold.group(1).strip(), bold.group(2).strip()
        head = head.rstrip(":").strip()

        head_links = parse_links(head)
        if head_links:
            # '- **[Name](url)** — description' : one named thing plus a sentence
            note = re.sub(r"^[—–-]\s*", "", rest).strip()
            current["stops"].append({
                "kind": "note",
                "link": head_links[0],
                "note": note,
            })
        else:
            current["stops"].append({
                "kind": "list",
                "label": head,
                "venues": parse_links(rest),
            })

    return sections


# -------------------------------------------------------------- rendering ---

def render_chip(venue: dict) -> str:
    note = f'<span class="note">{esc(venue["note"])}</span>' if venue.get("note") else ""
    return (
        f'<a class="chip" data-leaf href="{esc(venue["url"])}" '
        f'target="_blank" rel="noopener">{esc(venue["name"])}{note}{ARROW}</a>'
    )


def render_stop(stop: dict) -> str:
    if stop["kind"] == "note":
        link = stop["link"]
        note = f'<p class="stop-note">{esc(stop["note"])}</p>' if stop["note"] else ""
        return (
            '        <div class="stop stop--note" data-item>\n'
            f'          <a class="stop-title" data-label href="{esc(link["url"])}" '
            f'target="_blank" rel="noopener">{esc(link["name"])}{ARROW}</a>\n'
            f'          {note}\n'
            '        </div>'
        )

    chips = "".join(render_chip(v) for v in stop["venues"])
    return (
        '        <div class="stop" data-item>\n'
        f'          <span class="stop-label" data-label>{esc(stop["label"])}</span>\n'
        f'          <div class="chips">{chips}</div>\n'
        '        </div>'
    )


def stop_count(stop: dict) -> int:
    return 1 if stop["kind"] == "note" else len(stop["venues"])


def render_lines(sections):
    blocks = []
    for index, section in enumerate(sections):
        _, short, colour = LINES[index]
        slug = f"line-{index}"
        total = sum(stop_count(s) for s in section["stops"])
        stops = "\n".join(render_stop(s) for s in section["stops"])
        blocks.append(
            f'      <section class="line" id="{slug}" data-group="{slug}" '
            f'style="--accent: var(--{colour})" aria-labelledby="{slug}-h">\n'
            '        <div class="line-head">\n'
            f'          <h2 id="{slug}-h">{esc(section["title"])}</h2>\n'
            f'          <span class="line-count" data-count>{total}</span>\n'
            '        </div>\n'
            '        <div class="line-body">\n'
            f'{stops}\n'
            '        </div>\n'
            '      </section>'
        )
    return "\n\n".join(blocks)


def render_pills(sections):
    pills = [
        '          <button type="button" class="pill" data-filter="all" '
        'aria-pressed="true">All</button>'
    ]
    for index, _section in enumerate(sections):
        _, short, colour = LINES[index]
        pills.append(
            f'          <button type="button" class="pill" data-filter="line-{index}" '
            f'aria-pressed="false" style="--accent: var(--{colour})">'
            f'<i aria-hidden="true"></i>{esc(short)}</button>'
        )
    return "\n".join(pills)


# ------------------------------------------------------------------ shell ---

def icon(name: str, cls: str = "") -> str:
    paths = {
        "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
        "close": '<path d="M6 6l12 12M18 6L6 18"/>',
        "moon": '<path d="M20 14.5A8.5 8.5 0 019.5 4a8.5 8.5 0 1010.5 10.5z"/>',
        "sun": ('<circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.4M12 19.6V22M2 12h2.4'
                'M19.6 12H22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M19.1 4.9l-1.7 1.7'
                'M6.6 17.4l-1.7 1.7"/>'),
        "calendar": ('<rect x="3.5" y="5" width="17" height="15.5" rx="2.5"/>'
                     '<path d="M3.5 10h17M8 3v4M16 3v4"/>'),
        "dice": ('<rect x="3.5" y="3.5" width="17" height="17" rx="4"/>'
                 '<circle cx="8.5" cy="8.5" r="1.4" fill="currentColor" stroke="none"/>'
                 '<circle cx="15.5" cy="15.5" r="1.4" fill="currentColor" stroke="none"/>'
                 '<circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/>'),
        "up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
        "back": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    }
    klass = f' class="{cls}"' if cls else ""
    return (
        f'<svg{klass} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths[name]}</svg>'
    )


def theme_boot() -> str:
    """Applied before first paint so the page never flashes the wrong theme."""
    return (
        "(function(){try{var t=localStorage.getItem('lfg-theme');"
        "if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t);}"
        "catch(e){}})();"
    )


def document(title: str, description: str, body: str, extra_head: str = "") -> str:
    fonts = FONTS_CSS.read_text(encoding="utf-8").strip()
    theme = THEME_CSS.read_text(encoding="utf-8").strip()
    app = APP_JS.read_text(encoding="utf-8").strip()

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{esc(description)}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#E4E8EE" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0D1117" media="(prefers-color-scheme: dark)">
<title>{esc(title)}</title>
<script>{theme_boot()}</script>
<style>
{fonts}

{theme}
</style>{extra_head}
</head>
<body>
{body}
<button type="button" class="to-top" id="to-top" aria-label="Back to top">{icon('up')}</button>
<script>
{app}
</script>
</body>
</html>
"""


def toolbar(placeholder: str, cta_href: str, cta_label: str, cta_icon: str,
            pills: str, surprise: bool) -> str:
    surprise_btn = (
        f'''        <button type="button" class="tool-btn tool-btn--icon" id="surprise"
                title="Pick somewhere at random" aria-label="Pick somewhere at random">{icon('dice')}</button>
'''
        if surprise else ""
    )
    return f"""  <div class="toolbar">
    <div class="toolbar-row">
      <div class="search">
        <span class="search-icon">{icon('search')}</span>
        <label class="visually-hidden" for="search">Search</label>
        <input id="search" type="search" autocomplete="off" spellcheck="false"
               placeholder="{esc(placeholder)}">
        <span class="search-hint" aria-hidden="true">Press <kbd>/</kbd></span>
        <button type="button" class="search-clear" id="search-clear"
                aria-label="Clear search">{icon('close')}</button>
      </div>
{surprise_btn}      <button type="button" class="tool-btn tool-btn--icon" id="theme-toggle"
              aria-label="Switch theme">{icon('sun', 'icon-sun')}{icon('moon', 'icon-moon')}</button>
      <a class="tool-btn tool-btn--cta" href="{cta_href}">{icon(cta_icon)}<span class="label">{esc(cta_label)}</span></a>
    </div>
    <div class="pills" role="group" aria-label="Filter by category">
{pills}
    </div>
  </div>
"""


# ------------------------------------------------------------------ pages ---

def build_guide(sections) -> str:
    total = sum(stop_count(s) for section in sections for s in section["stops"])
    body = f"""<div class="page">
  <header class="masthead">
    <p class="eyebrow">A running list &middot; still growing</p>
    <h1 class="title">LONDON<span>FIELD GUIDE</span></h1>
    <p class="dek">Everything worth doing around the city, kept in one place &mdash; games and
      competitive socialising, rooftops, markets, festivals and the seasonal stuff that only
      comes round once a year. Search it, filter it, or hit the dice for something at random.</p>
    <p class="legend">
      <span><b id="result-count">{total}</b> <span id="result-noun" data-default="spots">spots</span></span>
      <span class="legend-sep" aria-hidden="true"></span>
      <span><b>{len(sections)}</b> categories</span>
      <span class="legend-sep" aria-hidden="true"></span>
      <span>every entry links straight to the venue</span>
    </p>
  </header>

{toolbar('Search 222 spots — try "golf", "rooftop", "Soho"'.replace('222', str(total)),
         'events-2026.html', 'Events', 'calendar', render_pills(sections), surprise=True)}
  <main class="lines">
{render_lines(sections)}
  </main>

  <div class="empty">
    <h2>Nothing matches &ldquo;<span id="empty-query"></span>&rdquo;</h2>
    <p>Try a shorter word, or a neighbourhood like Shoreditch or Peckham.</p>
    <button type="button" id="reset">Show everything</button>
  </div>

  <footer class="colophon">
    <span>Built from <a href="london-activities.md">london-activities.md</a></span>
    <span>Last built {BUILT_ON}</span>
  </footer>
</div>"""

    return document(
        "London Field Guide",
        f"A curated, growing list of {total} things to do in London — games, bars, "
        "rooftops, markets and festivals, each linked to the venue.",
        body,
    )


def build_events() -> str:
    main = EVENTS_MAIN.read_text(encoding="utf-8")

    # month sections become stops on the year, coloured by season
    def retint(match):
        month_id = match.group(1)
        season = MONTH_SEASON[month_id]
        return (f'<section class="month-group" id="{month_id}" data-group="{month_id}" '
                f'style="--accent: var(--season-{season})"')

    main = re.sub(
        r'<section class="month-group" id="(m-[a-z]{3})"[^>]*',
        retint,
        main,
    )
    main = main.replace('<div class="event-card">', '<div class="event-card" data-item>')
    main = main.replace('<span class="count">', '<span class="count" data-count>')

    # months with nothing booked in yet are drawn quiet rather than loud
    def quieten(block):
        if 'month-empty' in block.group(0):
            return block.group(0).replace('class="month-group"', 'class="month-group is-quiet"')
        return block.group(0)

    main = re.sub(r'<section class="month-group".*?</section>', quieten, main, flags=re.S)

    # look inside each section on its own — a shared regex would happily run past the
    # end of one month and pick up the next month's emptiness
    empties = {
        block.group(1)
        for block in re.finditer(r'<section class="month-group[^>]*id="(m-[a-z]{3})".*?</section>',
                                 main, flags=re.S)
        if 'month-empty' in block.group(0)
    }

    pills = ['          <button type="button" class="pill" data-filter="all" '
             'aria-pressed="true">Whole year</button>']
    for month_id, short in MONTHS:
        season = MONTH_SEASON[month_id]
        quiet = ' disabled' if month_id in empties else ''
        pills.append(
            f'          <button type="button" class="pill" data-filter="{month_id}"'
            f' aria-pressed="false" style="--accent: var(--season-{season})"{quiet}>'
            f'<i aria-hidden="true"></i>{short}</button>'
        )

    total = main.count('class="event-card"')
    pill_markup = "\n".join(pills)

    body = f"""<div class="page">
  <a class="back-link" href="london-guide.html">{icon('back')} Back to the field guide</a>

  <header class="masthead">
    <p class="eyebrow">Annual events &middot; London</p>
    <h1 class="title">EVENTS<span>2026</span></h1>
    <p class="dek">Festivals, markets and seasonal one-offs worth planning around, laid out
      month by month. Anything without a confirmed date is marked TBC and gets tightened up
      as organisers announce them.</p>
    <p class="legend">
      <span><b id="result-count">{total}</b> <span id="result-noun" data-default="events">events</span></span>
      <span class="legend-sep" aria-hidden="true"></span>
      <span><b>{len(MONTHS) - len(empties)}</b> months with something on</span>
    </p>
    <nav class="years" aria-label="Choose year">
      <span class="years-label">Year</span>
      <a href="events-2026.html" aria-current="true">2026</a>
      <span class="year-pill year-pill--future">2027 &middot; coming later</span>
    </nav>
  </header>

{toolbar('Search the year — try "market", "fireworks", "free"',
         'london-guide.html', 'Guide', 'search', pill_markup, surprise=False)}
{main}
  <div class="empty">
    <h2>Nothing matches &ldquo;<span id="empty-query"></span>&rdquo;</h2>
    <p>Try a broader word, or clear the month filter.</p>
    <button type="button" id="reset">Show the whole year</button>
  </div>

  <footer class="colophon">
    <span>Part of the <a href="london-guide.html">London Field Guide</a></span>
    <span>TBC entries update as organisers confirm dates</span>
  </footer>
</div>"""

    return document(
        "London Events 2026 — Field Guide",
        "A month-by-month calendar of London festivals, markets and seasonal events in 2026.",
        body,
    )


def main() -> None:
    sections = parse_markdown(SOURCE_MD)
    if len(sections) != len(LINES):
        raise SystemExit(
            f"markdown has {len(sections)} sections but LINES defines {len(LINES)}"
        )

    guide = build_guide(sections)
    (ROOT / "index.html").write_text(guide, encoding="utf-8")
    (ROOT / "london-guide.html").write_text(guide, encoding="utf-8")
    (ROOT / "events-2026.html").write_text(build_events(), encoding="utf-8")

    venues = sum(stop_count(s) for section in sections for s in section["stops"])
    print(f"guide     {venues} entries across {len(sections)} categories")
    for index, section in enumerate(sections):
        count = sum(stop_count(s) for s in section["stops"])
        print(f"  {LINES[index][1]:<16} {count:>3}")


if __name__ == "__main__":
    main()
