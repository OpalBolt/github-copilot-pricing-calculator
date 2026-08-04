# 07 — README

## Blocked by

- `02-provider-table.md`

## What to build

Update `README.md` to describe the three-tool site. The README follows the
same structure as today — intro, tool descriptions, data sources, project
layout, build instructions. Only the parts that changed are touched.

Changes from the current (two-tool) README:

### Intro

- "two-tool site" becomes "three-tool site".
- The list of calculators adds Provider comparison.

### The tools section

Add a new subsection:

```
### Provider comparison

Compares DeepSeek and z.ai side by side. Enter a budget and a token mix. The
table shows the effective tokens per dollar for every model across pay-per-token
and subscription plans. A tier selector and off-peak toggle adjust the devpack
math. Filter by provider or show all models.
```

### Data sources

Add a third bullet for the provider comparison:

```
- **Provider comparison** — scrapes DeepSeek and z.ai pricing pages into
  `providers.json`.
```

Add a line: `fetch_providers.py` writes `providers.json`.

### Project structure

Add the new files:

```
fetch_providers.py           # DeepSeek + z.ai scrapers -> providers.json
providers.json               # Provider comparison data (checked in)
```

Add to `docs/`:

```
  provider-compare.html      # Provider comparison
```

### Updating data

Add `python fetch_providers.py` to the list of safe-to-re-run scripts.

## Style rules

- American spelling. Short sentences. Active voice.
- No marketing adjectives (seamless, powerful, robust).
- No "this section covers…" throat-clearing. Start with the content.
- One idea per sentence. ~25 word max for descriptions, ~20 for instructions.
- Code blocks get a language tag.
- Descriptive link text, never "click here".

## Acceptance criteria

- [ ] README says "three-tool site" in the intro.
- [ ] Provider comparison subsection exists under The tools.
- [ ] Data sources list includes the provider comparison scraper.
- [ ] Project structure shows `fetch_providers.py`, `providers.json`, and
  `docs/provider-compare.html`.
- [ ] Build commands are unchanged (already cover all tools).
- [ ] Updating data section lists `python fetch_providers.py`.
- [ ] No marketing adjectives, no AI slop, no passive voice with a known
  actor.
