<!-- Trimmed copy of https://docs.mistral.ai/inference/pricing.md (fetched
2026-10-19) for parser tests: the four section tables with every published
shape — the sale-price row (Mistral Large 4), plain rows without a cached
rate (Mistral Large 3, Ministral 3 3B), third-party hosted cached-input
pricing (Z.ai GLM 5.3), the per-page, per-minute, and per-character
specialized rows, the free moderation row, and the input-only embedding
row. All kept rows are published numbers. -->

# API pricing

## Flagship models

Premier frontier models for the most demanding workloads.

| Model | API name | Price |
| --- | --- | --- |
| [Mistral Large 4](/models/mistral-large-4-0) | `mistral-large-4` | Input $0.68 /M Tokens (sale price, regular $1.36)<br>Cached input $0.07 /M Tokens (sale price, regular $0.14)<br>Output $2.09 /M Tokens (sale price, regular $4.18) |
| [Mistral Large 3](/models/mistral-large-3-25-12) | `mistral-large-2512` | Input $0.5 /M Tokens<br>Output $1.5 /M Tokens |
| [Ministral 3 3B](/models/ministral-3-3b-25-12) | `ministral-3b-2512` | Input $0.1 /M Tokens<br>Output $0.1 /M Tokens |

## Specialized models

Models built for specific tasks such as vision, OCR, and audio.

| Model | API name | Price |
| --- | --- | --- |
| [OCR 4.1](/models/ocr-4-1) | `mistral-ocr-4-1` | Input $4 /1000 Pages<br>Input $5 /1000 Annotated Pages |
| [Voxtral Mini Transcribe 2](/models/voxtral-mini-transcribe-26-02) | `voxtral-mini-2602` | Input $0.003 /Min |
| [Voxtral TTS](/models/voxtral-tts-26-03) | `voxtral-mini-tts-2603` | Input $0 /M Chars<br>Output $16 /M Chars |
| [Mistral Moderation 2](/models/mistral-moderation-26-03) | `mistral-moderation-2603` | Free<br>$0 /M Tokens |

## Third-party hosted

Third-party models hosted by Mistral.

| Model | API name | Price |
| --- | --- | --- |
| [Z.ai GLM 5.3](/models/zai-glm-5-3) | `zai-glm-5-3` | Input $1.4 /M Tokens<br>Cached input $0.14 /M Tokens<br>Output $4.4 /M Tokens |

## Code models

| Model | API name | Price |
| --- | --- | --- |
| [Codestral](/models/codestral-25-08) | `codestral-2508` | Input $0.3 /M Tokens<br>Output $0.9 /M Tokens |
| [Codestral Embed](/models/codestral-embed-25-05) | `codestral-embed-2505` | Input $0.15 /M Tokens |
