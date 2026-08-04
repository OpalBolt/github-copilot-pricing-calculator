# 05 — Filters and sort

## Blocked by

- `02-provider-table.md`

## What to build

Add client-side filtering and sorting to the provider comparison table.

### "Show all models" toggle

A chip toggle that reveals models with `default_visible: false`. Default
state: off — only models with `default_visible: true` are shown. When toggled
on, all models appear.

The toggle text comes from the data: count how many hidden models exist
(e.g. "Show 11 more models").

### Model search

A text input that filters rows by model id or provider name. Typing filters
the visible rows in real time — no debounce needed for a static table.

### Column sort

Clicking a column header sorts the table by that column. Clicking again
reverses the sort direction. The Effective tokens/$ column sorts numerically.
Price columns sort numerically. Provider, Plan, and Model columns sort
alphabetically.

A sort indicator (↑/↓) shows the current sort column and direction.

### Provider filter chips

A row of chips, one per provider. Clicking a chip toggles that provider's
rows on/off. Default: all providers visible. This is generated dynamically
from the `providers` array.

### Files

- `templates/provider-compare.app.js.j2` — extended with filter and sort
  logic.
- `templates/provider-compare.html.j2` — filter chips and search input wired
  to JS.

## Acceptance criteria

- [ ] "Show all models" toggle reveals hidden models when clicked.
- [ ] Toggle shows the count of hidden models.
- [ ] Search input filters rows by model id and provider name in real time.
- [ ] Column headers sort the table when clicked. Second click reverses.
- [ ] Sort indicator shows current column and direction.
- [ ] Provider filter chips toggle visibility of all rows for that provider.
- [ ] All filters work together (search + provider chips + show-all).
