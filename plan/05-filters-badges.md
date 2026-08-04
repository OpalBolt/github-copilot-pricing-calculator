# Filters, search, and row badges

## Parent

`plan/plan.md` — Cortecs price calculator (sister site).

## What to build

Add the interactivity that makes the table searchable. Filter chips narrow the list: Sovereign-only, ZDR, reasoning, tools, vision, audio. A free-text box searches model name and owner. A click on a column header sorts the table. Toggles show or hide the input, cached, and output columns.

The model row carries small badges for its capabilities: reasoning, tools, vision, audio. It also carries a muted quant chip when the cheapest provider uses heavy compression (`fp4` or `int4`). Full-quality quants (`fp16`, `bf16`, `fp8`) stay quiet. The drill-down always shows the full detail.

See `plan/plan.md` under "UI" and "Edge cases" for the chip list and the quant rule.

## Acceptance criteria

- [ ] Filter chips narrow the table: Sovereign-only, ZDR, reasoning, tools, vision, audio.
- [ ] A free-text search filters by model name and owner.
- [ ] A click on a column header sorts the table.
- [ ] Toggles show or hide the input, cached, and output columns.
- [ ] Each model row shows capability badges.
- [ ] A model row shows a muted `fp4` or `int4` chip when its cheapest provider uses that compression.
- [ ] Full-quality quants do not show a chip on the row.
- [ ] Filters, search, sort, and column toggles combine without conflict.

## Blocked by

`04-provider-drilldown.md` — the Sovereign-only and ZDR chips need the derived provider table.
