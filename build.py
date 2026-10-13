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

BUILT_ON = "13 Oct 2026"

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

# Kenny's own marks, written straight after a link: [Bounce](url){rec}
#   {rec}       been, loved it, would send people
#   {featured}  on the want-to-do list / one that looks interesting
KENNY_TAGS = re.compile(r"^(?:\s*\{(rec|featured)\})+")
KENNY_BADGES = {
    "rec": ("&#9733; Kenny recommends", "Kenny has been and loved it"),
    "featured": ("&#9670; Featured", "On Kenny&#x27;s want-to-do list"),
}


def take_tags(text: str) -> tuple[list[str], str]:
    """Split leading {rec}/{featured} tags off `text`."""
    m = KENNY_TAGS.match(text)
    if not m:
        return [], text
    return re.findall(r"\{(rec|featured)\}", m.group(0)), text[m.end():]


def badges(tags) -> str:
    return "".join(
        f'<span class="kenny kenny--{t}" title="{KENNY_BADGES[t][1]}">{KENNY_BADGES[t][0]}</span>'
        for t in ("rec", "featured") if t in tags)


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
        if match.start() < cursor:
            continue
        between = value[cursor:match.start()]
        note = between.strip().strip(",").strip()
        if note and items:
            items[-1]["note"] = note
        tags, after = take_tags(value[match.end():])
        items.append({"name": match.group(1).strip(), "url": match.group(2).strip(), "note": "",
                      "tags": tags})
        cursor = len(value) - len(after)

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
            # '- **[Name](url)**{rec} — description' : one named thing plus a sentence
            tags, rest = take_tags(rest)
            head_links[0]["tags"] = sorted(set(head_links[0]["tags"]) | set(tags))
            note = re.sub(r"^[—–-]\s*", "", rest.strip()).strip()
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
    tags = venue.get("tags") or []
    marked = "".join(f" is-{t}" for t in tags)
    # dead links stay as references but can't be picked for a plan
    pick = "" if "link dead" in venue.get("note", "").lower() else \
        f' data-pick="{short_id("p", venue["url"], venue["name"])}"'
    return (
        f'<a class="chip{marked}" data-leaf{pick} href="{esc(venue["url"])}" '
        f'target="_blank" rel="noopener">{esc(venue["name"])}{badges(tags)}{note}{ARROW}</a>'
    )


def render_stop(stop: dict) -> str:
    if stop["kind"] == "note":
        link = stop["link"]
        pick = "" if "link dead" in stop["note"].lower() else \
            f' data-pick="{short_id("p", link["url"], link["name"])}"'
        note = f'<p class="stop-note">{esc(stop["note"])}</p>' if stop["note"] else ""
        return (
            '        <div class="stop stop--note" data-item>\n'
            f'          <a class="stop-title" data-label{pick} '
            f'href="{esc(link["url"])}" '
            f'target="_blank" rel="noopener">{esc(link["name"])}{ARROW}</a>{badges(link.get("tags") or [])}\n'
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
        if short == "Resources":  # listings sites, not things to do
            stops = re.sub(r' data-pick="[a-z0-9]{5}"', "", stops)
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
    <p class="swipe-cta"><a href="swipe.html">&#9829; Swipe together</a>
      <button type="button" class="pick-toggle" id="pick-toggle">&#10003; Pick together</button></p>
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


  <div class="pick-bar" id="pick-bar" hidden>
    <p class="pick-note" id="pick-note"></p>
    <div class="pick-row">
      <span class="pick-count" id="pick-count">0 picked</span>
      <button type="button" class="pick-cancel" id="pick-cancel">Cancel</button>
      <button type="button" class="pick-done" id="pick-done">Done</button>
    </div>
  </div>

  <footer class="colophon">
    <span>Built from <a href="london-activities.md">london-activities.md</a></span>
    <span>Last built {BUILT_ON}</span>
    <span>Data as JSON: <a href="api/index.json">api/index.json</a> &middot; <a href="api/guide.json">guide</a> &middot; <a href="api/events-2026.json">events</a></span>
  </footer>
</div>"""

    return document(
        "London Field Guide",
        f"A curated, growing list of {total} things to do in London — games, bars, "
        "rooftops, markets and festivals, each linked to the venue.",
        body,
    )


# ----------------------------------------------------------- event dates ---

DOW = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MONTH_NUM = {short.lower(): i + 1 for i, (_, short) in enumerate(MONTHS)}

# "Sat 28", "Fri 1 Jan 2027", "21 Aug", "Sun 1 Nov"
DATE_PART = re.compile(
    r"(?:(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s+)?(\d{1,2})"
    r"(?:\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)?"
    r"(?:\s+(\d{4}))?", re.I)


def _resolve(part, month: int, year: int, warnings: list, label: str):
    """One side of a date label → datetime.date. A side without its own month is
    placed in the section's month or a neighbour, whichever its weekday fits."""
    from datetime import date
    dow, day, mon, yr = part.groups()
    day = int(day)
    if mon:
        candidates = [(int(yr) if yr else year, MONTH_NUM[mon.lower()])]
    else:
        candidates = [(year, month)]
        for step in (-1, 1):
            m, y = month + step, year
            if m == 0: m, y = 12, year - 1
            if m == 13: m, y = 1, year + 1
            candidates.append((y, m))
    valid = []
    for y, m in candidates:
        try:
            valid.append(date(y, m, day))
        except ValueError:
            pass
    if not valid:
        return None
    if dow:
        fits = [d for d in valid if DOW[d.weekday()] == dow.lower()[:3]]
        if fits:
            return fits[0]
        warnings.append(f"{label!r}: {dow} {day} isn't that weekday")
    return valid[0]


def event_dates(label: str, month: int, year: int, warnings: list) -> dict:
    """Turn a card's date label into data attributes for the calendar view.

    Returns start/end (ISO), an explicit list of days for "Sat 17 & Sat 24",
    'opens' for "Opens Fri 13" / "From Tue 10", or 'undated' for TBC/month-only."""
    text = html.unescape(re.sub(r"<[^>]+>", "", label))
    text = text.replace("–", "-").replace("—", "-").replace("·", " ").strip()
    if "TBC" in text or not re.search(r"\d", text):
        return {"undated": "1"}

    opens = re.match(r"(?i)(opens|from)\s+", text)
    if opens:
        text = text[opens.end():]

    if "-" in text:
        left, right = (s.strip() for s in text.split("-", 1))
        lm, rm = DATE_PART.search(left), DATE_PART.search(right)
        if not (lm and rm):
            warnings.append(f"{label!r}: can't read range")
            return {"undated": "1"}
        end = _resolve(rm, month, year, warnings, label)
        # an unmarked left side sits in the section month (or the one its weekday fits)
        start = _resolve(lm, month, year, warnings, label)
        if end and start and end < start and not rm.group(4):
            end = end.replace(year=end.year + 1)
        if not (start and end):
            return {"undated": "1"}
        return {"start": start.isoformat(), "end": end.isoformat()}

    parts = list(DATE_PART.finditer(text))
    days = [d for d in (_resolve(p, month, year, warnings, label) for p in parts) if d]
    if not days:
        return {"undated": "1"}
    out = {"start": days[0].isoformat(), "end": days[-1].isoformat()}
    if len(days) > 1:
        out["days"] = ",".join(d.isoformat() for d in days)
    if opens:
        out["opens"] = "1"
    return out


def date_attrs(main: str, year: int, warnings: list) -> str:
    """Stamp every event card with machine-readable dates from its label."""
    def per_section(sec):
        month = MONTH_NUM[sec.group(1)]

        def per_card(card):
            label = re.search(r'<span class="event-date">(.*?)</span>', card.group(0), re.S).group(1)
            attrs = event_dates(label, month, year, warnings)
            h3 = re.search(r"<h3>(.*?)</h3>", card.group(0), re.S)
            if h3 and attrs.get("start"):
                href = re.search(r'href="([^"]+)"', h3.group(1))
                name = plain(h3.group(1)).rstrip("\u2197").strip()
                attrs["pick"] = short_id("e", html.unescape(href.group(1)) if href else "", name, attrs["start"])
            extra = "".join(f' data-{k}="{v}"' for k, v in attrs.items())
            return re.sub(r'<div class="event-card"([^>]*)>', lambda m: f'<div class="event-card"{m.group(1)}{extra}>',
                          card.group(0), count=1)

        return re.sub(r'<div class="event-card"[^>]*>.*?</h3>',
                      per_card, sec.group(0), flags=re.S)

    return re.sub(r'<section class="month-group" id="m-([a-z]{3})".*?</section>',
                  per_section, main, flags=re.S)


def calendar_shell() -> str:
    """Empty frame for the month-grid view; app.js fills it from the cards."""
    days = "".join(f"<span>{d}</span>" for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    return f"""  <div class="view-switch" role="group" aria-label="View">
    <button type="button" class="view-btn" data-view="list" aria-pressed="true">List</button>
    <button type="button" class="view-btn" data-view="cal" aria-pressed="false">{icon('calendar')}Calendar</button>
  </div>

  <section class="cal" id="cal" hidden aria-label="Month calendar">
    <div class="cal-head">
      <button type="button" class="cal-nav" id="cal-prev" aria-label="Previous month">&#8249;</button>
      <h2 class="cal-title" id="cal-title" aria-live="polite"></h2>
      <button type="button" class="cal-nav" id="cal-next" aria-label="Next month">&#8250;</button>
      <button type="button" class="cal-today" id="cal-today">Today</button>
    </div>
    <div class="cal-weekdays" aria-hidden="true">{days}</div>
    <div class="cal-grid" id="cal-grid"></div>
    <div class="cal-day" id="cal-day"></div>
    <div class="cal-ongoing" id="cal-ongoing"></div>
  </section>
"""


# -------------------------------------------------------------------- api ---

def plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


RUNS_TO = re.compile(
    r"\b(?:to|until|till)\s+(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+(\d{4}))?", re.I)


def events_json(main: str, year: int) -> dict:
    """The calendar as data. `main` is the source after date_attrs() has run."""
    events = []
    for sec in re.finditer(r'<section class="month-group" id="m-([a-z]{3})".*?</section>', main, re.S):
        month = MONTH_NUM[sec.group(1)]
        for card in re.finditer(r'<div class="event-card"([^>]*)>(.*?)\n      </div>\n', sec.group(0), re.S):
            attrs = dict(re.findall(r'data-([a-z]+)="([^"]*)"', card.group(1)))
            inner = card.group(2)
            h3 = re.search(r"<h3>(.*?)</h3>", inner, re.S).group(1)
            link = re.search(r'href="([^"]+)"', h3)
            para = re.search(r"<p>(.*?)</p>", inner, re.S)
            # "Opens Fri 13 … Runs to 16 May": the opening day is the start, the
            # description carries the real end — so a date query finds it mid-run
            if "opens" in attrs and para:
                runs = RUNS_TO.search(plain(para.group(1)))
                if runs:
                    from datetime import date
                    start = date.fromisoformat(attrs["start"])
                    y = int(runs.group(3)) if runs.group(3) else start.year
                    try:
                        end = date(y, MONTH_NUM[runs.group(2)[:3].lower()], int(runs.group(1)))
                        if end < start and not runs.group(3):
                            end = end.replace(year=end.year + 1)
                        attrs["end"] = end.isoformat()
                    except ValueError:
                        pass
                else:
                    attrs["end"] = None  # open-ended: running from its opening day
            events.append({
                "name": plain(h3).rstrip("↗").strip(),
                "url": html.unescape(link.group(1)) if link else None,
                "month": month,
                "when": plain(re.search(r'<span class="event-date">(.*?)</span>', inner, re.S).group(1)),
                "start": attrs.get("start"),
                "end": attrs.get("end"),
                "days": attrs["days"].split(",") if "days" in attrs else None,
                "opens": "opens" in attrs,
                "dated": "undated" not in attrs,
                "description": plain(para.group(1)) if para else "",
                "recommended": "rec" in attrs.get("kenny", "").split(),
                "featured": "featured" in attrs.get("kenny", "").split(),
            })
    return {"year": year, "count": len(events), "events": events}


def guide_json(sections) -> dict:
    categories = []
    for index, section in enumerate(sections):
        entries = []
        for stop in section["stops"]:
            if stop["kind"] == "note":
                link = stop["link"]
                entries.append({"group": link["name"], "name": link["name"], "url": link["url"],
                                "note": stop["note"], "recommended": "rec" in link.get("tags", []),
                                "featured": "featured" in link.get("tags", [])})
            else:
                for v in stop["venues"]:
                    entries.append({"group": stop["label"], "name": v["name"], "url": v["url"],
                                    "note": v["note"], "recommended": "rec" in v.get("tags", []),
                                    "featured": "featured" in v.get("tags", [])})
        categories.append({"name": section["title"], "short": LINES[index][1],
                           "count": len(entries), "entries": entries})
    return {"count": sum(c["count"] for c in categories), "categories": categories}


def write_api(guide: dict, events: dict) -> None:
    import json
    api = ROOT / "api"
    api.mkdir(exist_ok=True)
    index = {
        "name": "London Field Guide API",
        "about": "Read-only JSON, regenerated by build.py on every deploy.",
        "updated": BUILT_ON,
        "endpoints": {
            "guide": {"path": "api/guide.json", "count": guide["count"]},
            f"events-{events['year']}": {"path": f"api/events-{events['year']}.json",
                                         "count": events["count"]},
        },
    }
    for name, data in [("index", index), ("guide", guide), (f"events-{events['year']}", events)]:
        (api / f"{name}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


EVENTS_DATA: dict = {}


def build_events() -> str:
    main = EVENTS_MAIN.read_text(encoding="utf-8")
    warnings: list[str] = []
    main = date_attrs(main, 2026, warnings)
    for w in warnings:
        print(f"warning: events-2026 {w}")
    EVENTS_DATA.update(events_json(main, 2026))

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
    main = main.replace('<div class="event-card"', '<div class="event-card" data-item')

    def kenny_badges(card):
        tags = card.group(1).split()
        return card.group(0).replace("</h3>", badges(tags) + "</h3>", 1)

    main = re.sub(r'<div class="event-card"[^>]*data-kenny="([^"]*)".*?</h3>', kenny_badges, main, flags=re.S)
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
    <p class="swipe-cta"><a href="swipe.html">&#9829; Swipe together</a>
      <button type="button" class="pick-toggle" id="pick-toggle">&#10003; Pick together</button></p>
    <nav class="years" aria-label="Choose year">
      <span class="years-label">Year</span>
      <a href="events-2026.html" aria-current="true">2026</a>
      <span class="year-pill year-pill--future">2027 &middot; coming later</span>
    </nav>
  </header>

{toolbar('Search the year — try "market", "fireworks", "free"',
         'london-guide.html', 'Guide', 'search', pill_markup, surprise=False)}
{calendar_shell()}
{main}
  <div class="empty">
    <h2>Nothing matches &ldquo;<span id="empty-query"></span>&rdquo;</h2>
    <p>Try a broader word, or clear the month filter.</p>
    <button type="button" id="reset">Show the whole year</button>
  </div>


  <div class="pick-bar" id="pick-bar" hidden>
    <p class="pick-note" id="pick-note"></p>
    <div class="pick-row">
      <span class="pick-count" id="pick-count">0 picked</span>
      <button type="button" class="pick-cancel" id="pick-cancel">Cancel</button>
      <button type="button" class="pick-done" id="pick-done">Done</button>
    </div>
  </div>

  <footer class="colophon">
    <span>Part of the <a href="london-guide.html">London Field Guide</a></span>
    <span>TBC entries update as organisers confirm dates</span>
    <span>Data as JSON: <a href="api/index.json">api/index.json</a> &middot; <a href="api/guide.json">guide</a> &middot; <a href="api/events-2026.json">events</a></span>
  </footer>
</div>"""

    return document(
        "London Events 2026 — Field Guide",
        "A month-by-month calendar of London festivals, markets and seasonal events in 2026.",
        body,
    )


# ------------------------------------------------------------------ swipe ---

SWIPE_JS = BUILD / "swipe.js"
ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"


def short_id(*parts: str, length: int = 5) -> str:
    """A stable 5-char id from the entry's own details, so a share link made
    before a rebuild still points at the same cards after it."""
    import hashlib
    n = int(hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12], 16)
    out = ""
    for _ in range(length):
        n, r = divmod(n, 36)
        out += ID_ALPHABET[r]
    return out


def swipe_deck(guide: dict, events: dict) -> list[dict]:
    """Everything that can be a card: guide places (not the Resources links, not
    dead links) and dated events."""
    cards, seen = [], set()

    def add(card, *key):
        cid = short_id(*key)
        if cid in seen:  # the same place listed under two categories: one card is enough
            return
        seen.add(cid)
        card["id"] = cid
        cards.append(card)

    for index, cat in enumerate(guide["categories"]):
        if LINES[index][1] == "Resources":
            continue
        for e in cat["entries"]:
            if "link dead" in e["note"].lower():
                continue
            add({"k": "p", "n": e["name"], "u": e["url"], "c": cat["short"],
                 "l": LINES[index][2], "g": e["group"], "t": e["note"],
                 "r": int(e["recommended"]), "f": int(e["featured"])},
                "p", e["url"], e["name"])

    for ev in events["events"]:
        if not ev["dated"]:
            continue
        season = MONTH_SEASON[MONTHS[ev["month"] - 1][0]]
        add({"k": "e", "n": ev["name"], "u": ev["url"], "c": "Events",
             "l": f"season-{season}", "w": ev["when"], "t": ev["description"],
             "s": ev["start"], "e": ev["end"], "d": ev["days"],
             "r": int(ev["recommended"]), "f": int(ev["featured"])},
            "e", ev["url"] or "", ev["name"], ev["start"] or "")
    return cards


def build_swipe(guide: dict, events: dict) -> str:
    import json
    deck = swipe_deck(guide, events)
    data = json.dumps(deck, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    cats = [short for _, short, _ in LINES if short != "Resources"] + ["Events"]
    chips = "\n".join(
        f'        <button type="button" class="pill" data-cat="{esc(c)}" aria-pressed="false" '
        f'style="--accent: var(--{"season-autumn" if c == "Events" else next(col for _, s, col in LINES if s == c)})">'
        f'<i aria-hidden="true"></i>{esc(c)}</button>'
        for c in cats)
    script = SWIPE_JS.read_text(encoding="utf-8").strip()

    body = f"""<div class="page swipe-page">
  <a class="back-link" href="london-guide.html">{icon('back')} Back to the field guide</a>

  <header class="masthead masthead--tight">
    <p class="eyebrow">Swipe together &middot; London</p>
    <h1 class="title">WHAT SHALL<span>WE DO?</span></h1>
    <p class="dek">You each swipe the same cards on your own &mdash; no peeking at each other&rsquo;s.
      At the end you see what you <b>both</b> said yes to.</p>
  </header>

  <main class="swipe" id="swipe">

    <section class="sw-screen" data-screen="setup">
      <p class="sw-small">Rather tick from the whole guide? <a href="london-guide.html#pick">Pick together on the guide &rarr;</a></p>
      <div class="sw-field">
        <label class="sw-label" for="sw-name">Your name</label>
        <input id="sw-name" class="sw-input" type="text" maxlength="20" autocomplete="given-name" placeholder="e.g. Kenny">
      </div>
      <div class="sw-field">
        <span class="sw-label">When?</span>
        <div class="sw-seg" role="group" aria-label="When">
          <button type="button" class="pill" data-when="any" aria-pressed="true">Any time</button>
          <button type="button" class="pill" data-when="weekend" aria-pressed="false">This weekend</button>
          <button type="button" class="pill" data-when="date" aria-pressed="false">Pick a date</button>
        </div>
        <input id="sw-date" class="sw-input sw-date" type="date" hidden>
      </div>
      <div class="sw-field">
        <span class="sw-label">What kind of thing? <small>(leave all off for everything)</small></span>
        <div class="sw-chips" role="group" aria-label="Categories">
{chips}
        </div>
      </div>
      <div class="sw-field">
        <span class="sw-label">How many cards?</span>
        <div class="sw-seg" role="group" aria-label="Deck size">
          <button type="button" class="pill" data-size="15" aria-pressed="false">15</button>
          <button type="button" class="pill" data-size="25" aria-pressed="true">25</button>
          <button type="button" class="pill" data-size="40" aria-pressed="false">40</button>
        </div>
      </div>
      <button type="button" class="sw-go" id="sw-start">Start swiping</button>
      <p class="sw-small">Got a link or code from someone? <button type="button" class="sw-linkbtn" data-goto="join">Join their session</button></p>
    </section>

    <section class="sw-screen" data-screen="join" hidden>
      <p class="sw-lead">Paste the link or code you were sent.</p>
      <textarea id="sw-code" class="sw-input sw-code" rows="3" spellcheck="false" placeholder="https://…/swipe.html#…"></textarea>
      <p class="sw-error" id="sw-join-error" hidden></p>
      <button type="button" class="sw-go" id="sw-join">Join</button>
      <p class="sw-small"><button type="button" class="sw-linkbtn" data-goto="setup">&larr; Start a new one instead</button></p>
    </section>

    <section class="sw-screen" data-screen="invite" hidden>
      <p class="sw-lead" id="sw-invite-lead"></p>
      <div class="sw-field">
        <label class="sw-label" for="sw-name-b">Your name</label>
        <input id="sw-name-b" class="sw-input" type="text" maxlength="20" autocomplete="given-name">
      </div>
      <button type="button" class="sw-go" id="sw-invite-go">Start swiping</button>
    </section>

    <section class="sw-screen" data-screen="deck" hidden>
      <div class="sw-progress"><span id="sw-who"></span><span id="sw-count"></span></div>
      <div class="sw-bar"><i id="sw-bar"></i></div>
      <div class="sw-stack" id="sw-stack" aria-live="polite"></div>
      <div class="sw-actions">
        <button type="button" class="sw-btn sw-btn--no" id="sw-no" aria-label="Nope">&#10005;</button>
        <button type="button" class="sw-btn sw-btn--undo" id="sw-undo" aria-label="Undo last">&#8630;</button>
        <button type="button" class="sw-btn sw-btn--yes" id="sw-yes" aria-label="Yes">&#9829;</button>
      </div>
      <p class="sw-small sw-keys">Drag the card, tap the buttons, or use &larr; &rarr; keys.</p>
    </section>

    <section class="sw-screen" data-screen="handoff" hidden>
      <p class="sw-lead" id="sw-handoff-lead"></p>
      <div class="sw-share">
        <button type="button" class="sw-go" id="sw-share">Send to your partner</button>
        <button type="button" class="sw-go sw-go--ghost" id="sw-copy">Copy link</button>
      </div>
      <p class="sw-small" id="sw-handoff-small">They&rsquo;ll swipe the same cards without seeing yours, then you&rsquo;ll both see the matches.</p>
      <div class="sw-or"><span>or</span></div>
      <button type="button" class="sw-go sw-go--ghost" id="sw-pass">Same phone &mdash; pass it over</button>
    </section>

    <section class="sw-screen" data-screen="results" hidden>
      <div id="sw-results"></div>
      <div class="sw-share">
        <button type="button" class="sw-go" id="sw-share-results">Share the matches</button>
        <button type="button" class="sw-go sw-go--ghost" id="sw-again">Start again</button>
      </div>
    </section>

  </main>

  <footer class="colophon">
    <span>Part of the <a href="london-guide.html">London Field Guide</a> &middot; <a href="events-2026.html">Events</a></span>
    <span>Nothing is stored on a server &mdash; your picks live in the link you share</span>
  </footer>
</div>
<script type="application/json" id="sw-data">{data}</script>
<script>
{script}
</script>"""

    return document(
        "Swipe Together — London Field Guide",
        "Both swipe the same London plans on your own phones, then see what you both said yes to.",
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
    guide_data = guide_json(sections)
    write_api(guide_data, EVENTS_DATA)
    (ROOT / "swipe.html").write_text(build_swipe(guide_data, EVENTS_DATA), encoding="utf-8")

    venues = sum(stop_count(s) for section in sections for s in section["stops"])
    print(f"guide     {venues} entries across {len(sections)} categories")
    for index, section in enumerate(sections):
        count = sum(stop_count(s) for s in section["stops"])
        print(f"  {LINES[index][1]:<16} {count:>3}")


if __name__ == "__main__":
    main()
