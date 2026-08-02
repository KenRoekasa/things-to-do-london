# London Activities

An accumulating list of cool things to do in London.

[london-activities.md](london-activities.md) is the source of truth — a growing, curated list I keep adding to over time.

## Pages

- [index.html](index.html) / [london-guide.html](london-guide.html) — the field guide, generated from the markdown
- [events-2026.html](events-2026.html) — a month-by-month calendar, linked from the guide's toolbar. Future years get their own `events-YYYY.html`.

Both are single self-contained files: fonts, CSS and JS are inlined, so they open straight off the filesystem with no server and no network. Each has instant search, category filters, a light/dark theme toggle that remembers your choice, and a layout that works on phone, tablet and desktop.

## Rebuilding

After editing `london-activities.md`:

```sh
python3 build.py
```

That rewrites all three HTML files. The shared pieces live in `build/`:

| file | what it is |
| --- | --- |
| `build/theme.css` | the design system — colour tokens, type scale, the route-line layout |
| `build/app.js` | search, filtering, theme toggle |
| `build/fonts.css` | the two embedded typefaces, base64-inlined |
| `build/events-2026.main.html` | the event data for 2026 (hand-maintained, not derived from the markdown) |

Event entries are edited directly in `build/events-2026.main.html`, then picked up by the build.
