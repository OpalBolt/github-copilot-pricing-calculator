# Landing hub and tool relocation

## Parent

`plan/plan.md` — Cortecs price calculator (sister site).

## What to build

A landing page replaces the current site root. It shows two cards: one for the GitHub Copilot calculator, one for the Cortecs calculator. Each card links to its tool page.

The existing GitHub tool moves off the root to its own page so the root can hold the hub. The hub does not advertise that the site compares multiple tools. Each calculator is just one linked option. Each tool page links back to the hub.

The generator renders the hub from the shared templates. See `plan/plan.md` under "Landing page" for the locked decision and the file map.

## Acceptance criteria

- [ ] The site root renders a hub with two cards.
- [ ] One card links to the GitHub Copilot calculator page.
- [ ] One card links to the Cortecs calculator page.
- [ ] The GitHub tool moves off the root to its own page and still works there.
- [ ] Each tool page links back to the hub.
- [ ] The hub uses the shared stylesheet.

## Blocked by

`01-cortecs-model-table.md` — the hub links to the Cortecs page, so that page must exist first.
