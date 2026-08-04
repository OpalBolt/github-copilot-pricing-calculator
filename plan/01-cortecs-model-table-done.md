# Cortecs model table from the live API

## Parent

`plan/plan.md` — Cortecs price calculator (sister site).

## What to build

The first end-to-end slice. A fetch script calls the Cortecs models API, stores the result as JSON, and a page renders a table of every model with its cheapest input and output price.

Call the endpoint with `extended=true` so the response includes per-provider detail. Later slices use that detail. The top-level `pricing` object on each model already holds the cheapest provider's price, so the table shows that value directly. Add a one-line footnote under the table: prices are the cheapest available provider, and Cortecs also offers fastest and balanced routing.

The fetch script writes a JSON file and prints a short summary. It includes a `__main__` self-check that fails if the response lacks models or expected fields. The table renders in a default order (cheapest input price first) so it reads well before client-side sort lands in a later slice.

The generator renders the Cortecs page from that JSON. It reuses the existing Jinja2 pipeline and runs with or without the network fetch, like the GitHub tool. See `plan/plan.md` for the endpoint URL, the data shape, and the file map.

## Acceptance criteria

- [ ] A fetch script writes the Cortecs models data to a JSON file.
- [ ] The fetch uses `extended=true` and `currency=EUR`.
- [ ] The fetch script has a `__main__` self-check that fails when the data lacks models or expected fields.
- [ ] The generator renders a Cortecs page that lists every model with its name, owner, and cheapest input and output price per 1M tokens.
- [ ] The page shows the "cheapest available / fastest-balanced routing" footnote.
- [ ] The table renders in a default order, cheapest input price first.
- [ ] Running the generator with `--no-fetch` rebuilds the page from the cached JSON.

## Blocked by

None. Can start immediately.
