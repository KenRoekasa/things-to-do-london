# London Activities

An accumulating list of cool things to do in London.

[london-activities.md](london-activities.md) is the source of truth — a growing, curated list I keep adding to over time.

## Pages

Published at <https://kenroekasa.github.io/things-to-do-london/>:

- `index.html` / `london-guide.html` — the field guide, generated from the markdown
- `events-2026.html` — a month-by-month calendar, linked from the guide's toolbar. Future years get their own `events-YYYY.html`.

Both are single self-contained files: fonts, CSS and JS are inlined, so they open straight off the filesystem with no server and no network. Each has instant search, category filters, a light/dark theme toggle that remembers your choice, and a layout that works on phone, tablet and desktop.

## Publishing

Push to `main` and the [Build and deploy](.github/workflows/deploy.yml) workflow runs `build.py` and publishes the pages. The HTML is generated in CI and not committed, so an edit to `london-activities.md` — including one made in GitHub's web editor on a phone — is all it takes.

## Building locally

To preview a change before pushing:

```sh
python3 build.py
xdg-open index.html
```

That writes all three HTML files (git-ignored). The shared pieces live in `build/`:

| file | what it is |
| --- | --- |
| `build/theme.css` | the design system — colour tokens, type scale, the route-line layout |
| `build/app.js` | search, filtering, theme toggle |
| `build/fonts.css` | the two embedded typefaces, base64-inlined |
| `build/events-2026.main.html` | the event data for 2026 (hand-maintained, not derived from the markdown) |

Event entries are edited directly in `build/events-2026.main.html`, then picked up by the build.

## Weekly emails

[Inbox and health check](.github/workflows/weekly.yml) runs every morning and posts two GitHub issues on Mondays (GitHub emails them to the repo owner):

- **📥 Inbox** — [`tools/inbox.py`](tools/inbox.py) reads the Londonist, Secret London and IanVisits feeds daily, keeps things-to-do posts (no gigs or concerts), drops anything already in the guide, and posts the week's finds as a checklist. Nothing is added to the site automatically. Tune what gets through with the `KEEP` / `DROP` word lists at the top of the script.
- **🩺 Site health** — [`tools/health.py`](tools/health.py) checks every link, plus calendar dates still marked TBC as their month arrives, dates flagged as unconfirmed, and guide notes like "opening Oct 2026" once they've passed. Each week's report closes the previous one.

Both run locally too: `python3 tools/health.py --dry-run` and `python3 tools/inbox.py preview`. Either can be triggered early from the Actions tab (**Run workflow**), which also posts.
