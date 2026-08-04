# Provider drill-down and sovereignty badges

## Parent

`plan/plan.md` — Cortecs price calculator (sister site).

## What to build

Let a visitor open any model to see its providers. A click on a model row expands a nested table beneath it. Each provider row shows its price, quantization, context size, supported features, and audio cost where present.

Two badges mark each provider: EU-sovereign and zero-data-retention. The API has no providers endpoint. The fetch derives a provider-attribute table by comparing three responses: the full model list, the `eu_native=true` list, and the `allow_zero_data_retention=true` list. A provider lands in the EU-sovereign set only if the first diff includes it, and in the ZDR set only if the second diff includes it.

The derived provider table ships inside the JSON. See `plan/plan.md` under "Sovereignty & ZDR" for the provider sets.

## Acceptance criteria

- [ ] A click on a model row expands a nested provider table; a second click collapses it.
- [ ] Each provider row shows input, cached, and output price.
- [ ] Each provider row shows quantization, context size, and supported features.
- [ ] Providers that carry an audio cost show it in the expanded row.
- [ ] Each provider row shows an EU-sovereign badge when the provider is EU-native.
- [ ] Each provider row shows a ZDR badge when the provider offers zero data retention.
- [ ] The fetch derives the provider-attribute table from the three API responses and writes it into the JSON.
- [ ] The fetch self-check confirms the provider table matches the known provider sets.

## Blocked by

`01-cortecs-model-table.md`.
