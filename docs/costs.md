# Estimated Daily AI Costs

This document provides a rough overview of how much it costs to process one day worth of data with the default OpenAI models.

## Daily Input
- **Images**: ~1&nbsp;GB of photos (~1000 images).
- **Text**: ~3&nbsp;MB of Telegram messages (~750k tokens).

## Captioning
Each image is sent to GPT‑4o with a short prompt. A single 1080 × 1080 photo counts for roughly 85 input tokens. With about 20 tokens of prompt and ~100 tokens in the response the total cost per image is around 225 tokens.

- **Input**: 125k tokens → `125k / 1M × $5 ≈ $0.63`
- **Output**: 100k tokens → `100k / 1M × $15 ≈ $1.50`

**Captioning total:** ~$2.1 per day.

## Chopping Posts
`chop.py` uses GPT‑4o‑mini to split messages into lots with a fallback to GPT‑4o when the result is incomplete or would be discarded during cleanup. The message text plus image captions add up to roughly 850k input tokens per day. The JSON output is about 100k tokens.

- **Input**: `850k / 1M × $5 ≈ $4.25`
- **Output**: `100k / 1M × $15 ≈ $1.50`

**Chopping total:** ~$5.8 per day.

## Embedding
Lots are embedded with `text-embedding-3-large`. At about 100k tokens per day the cost is negligible (`100k / 1M × $0.13 ≈ $0.013`).

## Grand Total
Roughly **$8 per day** for OpenAI API calls when processing 1&nbsp;GB of images and 3&nbsp;MB of text. Multiply by 30 for a monthly estimate of about **$240**. Costs can be reduced by skipping unchanged messages or batching updates less frequently.
