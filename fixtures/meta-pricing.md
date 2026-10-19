<!-- Trimmed copy of https://dev.meta.ai/docs/pricing-rate-limits.md (fetched
2026-10-19) for parser tests: the pricing-modes prose, the Standard-only Muse
Wonder table, the Standard-plus-Contributor Muse Spark table with its
contributor variant ids, and the per-image Muse Image table that prices no
tokens. All kept numbers are published. -->

# Pricing and rate limits

Use our models with pay-as-you-go billing on Meta Model API. This page covers
pay-as-you-go: Model API bills text models per token, image generation per
image.

## Pricing modes

Some models can be used in two modes. Standard mode uses standard pricing.
Contributor mode offers discounted pricing or more usage in exchange for
permission to use your content to train future Meta models.

### Standard mode

In Standard mode, you pay standard prices and your content is not used to
train Meta models. Every model on this page is available in Standard mode.

### Contributor mode

On Model API, Contributor mode runs the same models at heavily discounted
token prices, in exchange for permission to use your content to train future
Meta models.

On Model API, use Contributor mode with Muse Spark 1.3 or 1.2 by calling its
Contributor-mode variant: `muse-spark-1.3-contributor` or
`muse-spark-1.2-contributor`. Contributor mode isn't available for Muse
Wonder on Model API.

## Model pricing

### Muse Wonder

Model: `muse-wonder-1.0`.

| Usage        | Standard mode (per 1M tokens) | Contributor mode (per 1M tokens) |
| :----------- | :---------------------------- | :------------------------------- |
| Cached input | $0.20                         | Not available                    |
| Input        | $4.00                         | Not available                    |
| Output       | $20.00                        | Not available                    |

### Muse Spark

Models: `muse-spark-1.3`, `muse-spark-1.2`, and `muse-spark-1.1` in Standard
mode; `muse-spark-1.3-contributor` and `muse-spark-1.2-contributor` in
Contributor mode. Muse Spark 1.1 is Standard mode only.

| Usage        | Standard mode (per 1M tokens) | Contributor mode (per 1M tokens) |
| :----------- | :---------------------------- | :------------------------------- |
| Cached input | $0.15                         | $0.002                           |
| Input        | $1.25                         | $0.10                            |
| Output       | $4.25                         | $0.20                            |

### Muse Image

| Usage           | Price           |
| :-------------- | :-------------- |
| Generated image | $0.01 per image |

[Muse Image](https://dev.meta.ai/docs/models#muse-image) is billed at a flat
rate per generated image.
