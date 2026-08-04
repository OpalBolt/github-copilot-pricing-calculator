# Budget and cost columns in euros

## Parent

`plan/plan.md` — Cortecs price calculator (sister site).

## What to build

Bring over the budget machinery from the GitHub tool, priced in euros instead of AI credits.

A controls panel captures the total token count, the input/cached/output split, and a euro budget. For each model the page computes the estimated cost of one run. It also shows how many runs the budget buys, and a relative-cost bar scaled to the cheapest model in view.

Free models (price zero) break the runs calculation. Guard the math. Show "free" and skip the bar instead of dividing by zero.

The logic mirrors the GitHub tool. See `plan/plan.md` under "How pricing works" for the formulas, adjusted from credits to euros.

## Acceptance criteria

- [ ] A controls panel captures total tokens, input %, cached %, output %, and a euro budget.
- [ ] Each model row shows an estimated cost for one run of the configured token mix.
- [ ] Each model row shows how many runs the budget buys.
- [ ] A relative-cost bar scales to the cheapest model in the current view.
- [ ] Free models (price zero) show "free" and do not crash the runs math.
- [ ] Changing the controls updates every row.

## Blocked by

`01-cortecs-model-table.md`.
