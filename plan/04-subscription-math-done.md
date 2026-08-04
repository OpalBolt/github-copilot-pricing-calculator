# 04 — Subscription math

## Blocked by

- `02-provider-table.md`

## What to build

Wire up the subscription rows in the Effective tokens/$ column. Add the
devpack tier selector and off-peak toggle so they drive live recomputation.

### JS math

For each subscription provider row:

```
weekly_cost = monthly_cost / 4.33
weighted_mult = input_pct × mult_input + cached_pct × mult_cached + output_pct × mult_output
credits_per_1M_tokens = weighted_mult × 1_000_000 / 10_000
tokens_per_week = weekly_credits / credits_per_1M_tokens × 1_000_000
effective_price_per_1M = weekly_cost / (tokens_per_week / 1_000_000)
tokens_per_dollar = 1_000_000 / effective_price_per_1M
```

When off-peak is checked, multiply `credits_per_1M_tokens` by the provider's
`off_peak_multiplier` (0.5 for z.ai).

The effective $/1M prices are also shown in the Input/Cached/Output $/1M
columns (replacing the placeholders from slice 02).

### Controls

- **Subscription tier**: radio buttons (Lite/Pro/Max). Default: Lite. Only
  shown when a subscription provider is present. Changing the tier updates
  all subscription rows.
- **Off-peak toggle**: checkbox, off by default. Only shown when a
  subscription provider is present. Label comes from `off_peak_label` in the
  data.

Both controls appear only if the `providers` array contains at least one
entry with `pricing_type: "subscription"`. This is checked at template render
time — the HTML for these controls is conditionally included.

### Edge cases

- If multiple subscription providers exist with different tiers, the global
  tier selector still applies. This is noted as a known limitation
  (`# ponytail: per-provider tier selectors if tiers diverge`).

### Files

- `templates/provider-compare.app.js.j2` — extended with subscription math.
- `templates/provider-compare.html.j2` — tier selector and off-peak toggle
  wired to JS events.

## Acceptance criteria

- [ ] Selecting a devpack tier updates Effective tokens/$ for all
  subscription rows.
- [ ] Toggling off-peak halves the credit consumption and doubles the
  effective tokens/$.
- [ ] Effective $/1M values appear in the price columns for subscription
  rows.
- [ ] Tier selector and off-peak toggle do not render when no subscription
  provider exists in the data.
- [ ] Free models with all-zero multipliers show "Free".
