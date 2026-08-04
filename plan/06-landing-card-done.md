# 06 — Landing card

## Blocked by

- `02-provider-table.md`

## What to build

Add a third card to the landing hub (`docs/index.html`) that links to
`provider-compare.html`.

The landing page currently has two cards: GitHub Copilot calculator and
Cortecs price calculator. Add a third card for the Provider comparison tool.

### Card content

- **Title**: "Provider Comparison"
- **Blurb**: "DeepSeek vs z.ai — compare pay-per-token and subscription
  pricing. See what your budget gets you."
- **Link**: `provider-compare.html`
- **Visual**: use the same card style as the existing two cards.

### Generation

The landing page template (`landing.html.j2`) already loops over a list of
tool cards. Add a third entry to that list.

The link text and blurb are static — the card does not read from
`providers.json` at render time.

### Files

- `templates/landing.html.j2` — add third card.
- `generate_html.py` — already renders `docs/index.html` from this template;
  no changes needed if the template drives the card list.

## Acceptance criteria

- [ ] Landing page shows three cards in a grid.
- [ ] Third card reads "Provider Comparison" with the blurb above.
- [ ] Card links to `provider-compare.html`.
- [ ] Card uses the same visual style as the existing two.
- [ ] Existing two cards are unchanged.
