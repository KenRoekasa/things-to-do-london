# CLAUDE.md

A personal, accumulating list of things to do in London, published as static HTML.
There is no server, no framework and no dependencies — just Python 3 and the stdlib.

## The one rule

`london-activities.md` is the source of truth for venues. The HTML files are **generated
output** — never hand-edit `index.html`, `london-guide.html` or `events-2026.html`.

**Any change to content must be followed by a rebuild, in the same change:**

```sh
python3 build.py
```

It rewrites all three HTML files and prints a per-category entry count. The HTML is
**not committed** (it's git-ignored): on push to `main`, `.github/workflows/deploy.yml`
runs the same build and publishes the pages to GitHub Pages. The local build is the check —
it hard-fails on a malformed source, and its output is what you open to eyeball a change.

If the user adds something ("add X to the guide", "put Y in for September"), the job is
not done until the build has passed locally and the source edit is committed. Once pushed,
confirm the `Build and deploy` run went green (`gh run list --limit 1`) — a red or stuck
run means the live site is still on the old version.

## Layout

| path | role |
| --- | --- |
| `london-activities.md` | source of truth for venues — edit this |
| `build/events-2026.main.html` | source of truth for calendar events — hand-written HTML, *not* derived from the markdown |
| `build.py` | the whole build; parses the markdown, inlines the assets, writes the pages |
| `build/theme.css` | design system — colour tokens, type scale, route-line layout |
| `build/app.js` | search, category filtering, theme toggle |
| `build/fonts.css` | two typefaces, base64-inlined (~330 KB, don't reformat) |
| `.github/workflows/deploy.yml` | builds and publishes to GitHub Pages on push to `main` |
| `.github/workflows/weekly.yml` | daily: collect feed finds; Mondays: post the inbox + site-health issues |
| `tools/inbox.py` | discovery inbox — RSS feeds → filter → weekly `inbox` issue. State lives on the `inbox-state` branch |
| `tools/health.py` | dead links, TBCs coming due, unconfirmed dates, stale "opening…" notes → weekly `site-health` issue |
| `index.html`, `london-guide.html` | generated, git-ignored — byte-identical copies of the guide |
| `events-2026.html` | generated, git-ignored — the calendar |

Pages are fully self-contained: fonts, CSS and JS are inlined so they open straight off
the filesystem with no network. Keep it that way — no CDN links, no external requests.

## Adding a venue to the guide

Add a bullet under the right `##` section in `london-activities.md`. Two shapes parse:

```markdown
- **Category label:** [Name](url), [Name (Neighbourhood)](url), [Name](url) (a note)
- **[Single Venue](url)** — a sentence about it
```

Notes: text sitting *after* a link attaches to that link as a parenthetical. Put the
neighbourhood inside the link text (`[Bounce (Old Street)](url)`) — search indexes it, so
"Peckham" or "Soho" finds the venue.

Sections are matched to line colours **by position**, via the `LINES` list in `build.py`.
Adding, removing or reordering a `##` heading means updating `LINES` to match — the build
hard-fails with a section-count mismatch if you forget. Leading emoji in headings are
stripped by the parser and are cosmetic.

## Adding an event to the calendar

Edit `build/events-2026.main.html` directly, inside the right `<section class="month-group">`:

```html
<div class="event-card">
  <span class="event-date">Sat 12</span>
  <div class="event-body">
    <h3><a href="URL" target="_blank" rel="noopener">Name<span aria-hidden="true">&#8599;</span></a></h3>
    <p>Where &mdash; what it is.</p>
  </div>
</div>
```

- Adding the **first** event to an empty month: delete that month's
  `<div class="month-empty">…</div>`. The build detects empty months by that div and
  disables their filter pill, so leaving it in makes the new event unreachable by filter.
- The `<span class="count">` in the month head is recalculated by `app.js` on load, but
  set it correctly anyway so the page reads right before JS runs.
- Undated entries are marked TBC and tightened when organisers confirm.
- Season colours come from `MONTH_SEASON` in `build.py`; the `style="--accent:…"` in the
  source file is overwritten at build time, so don't fuss over it.
- A future year gets its own `build/events-YYYY.main.html` plus a `events-YYYY.html`
  target, and the year nav in `build_guide`/`build_events` updated.

## Conventions

- `BUILT_ON` in `build.py` is a hand-set date string in the guide footer. Bump it when
  making a substantive content pass.
- Entries link straight to the venue's own site where one exists; aggregator links
  (Time Out, DesignMyNight, Secret London) are a fallback for roundups.
- The build must stay stdlib-only and runnable on Python 3.11 — in particular, no
  backslashes inside f-string expressions (that needs 3.12+). Build a local variable first.
- Re-running `python3 build.py` with no source change must produce identical output
  (compare `md5sum *.html`). If it doesn't, something non-deterministic crept in.

## Checking the result

Open the file directly — `xdg-open index.html` — no server needed. Worth a look after a
content change: search still matches the new entry, its category pill filters it in, and
both light and dark themes look right.
