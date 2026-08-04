# 03 — Budget and token mix

## Blocked by

- `02-provider-table.md`

## What to build

Wire up the budget and token mix inputs so the **Effective tokens/$** column
computes live. The controls come from the same macros used by the Copilot and
Cortecs tools — number inputs, not range sliders.

### JS (`provider-compare.app.js.j2`)

**Paygo rows** (pricing_type: paygo):

```
blended_price = input_pct × input_price + cached_pct × cached_price + output_pct × output_price
tokens_per_dollar = 1_000_000 / blended_price
```

**Subscription rows**: leave as placeholder for slice 04.

### Controls

- **Budget**: number input. Default $10.
- **Token mix**: three number inputs for Input %, Cached %, Output %. Must
  sum to 100%. Show a warning if they do not.

All inputs trigger a re-render of the Effective tokens/$ column on change.

### Edge cases

- If token mix does not sum to 100%, show a warning next to the inputs but
  still compute with the raw values.
- If any price is zero (free model), display "Free" in the column instead of
  computing.
- If blended_price is zero, display "—".

### Files

- `templates/provider-compare.app.js.j2` — new JS file with the compute loop.
- `templates/provider-compare.html.j2` — extended to include the JS bundle.

## Acceptance criteria

- [ ] Changing the budget input updates the Effective tokens/$ column for all
  paygo rows.
- [ ] Changing any token mix input updates the column.
- [ ] A warning appears when Input + Cached + Output does not equal 100%.
- [ ] Free models show "Free" in the column.
- [ ] Subscription rows still show a placeholder (wired in slice 04).
