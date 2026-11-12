# Problem 4: With and Without Cached Tokens

**Model:** `gpt-6-luna` through Portkey
**Documents:** the 12 practice documents, each run once in each setup (same prompt, same tools)
**Raw data:** `output/cache_test.json`, which has one record for every model call: setup, document, the API's `usage` block exactly as returned, and dollars from `data/prices.json`
**Script:** `cache_test.py`

## 1. The two setups, and proof each did what it should

| Setup | How it is configured |
|---|---|
| `no_cache` | `prompt_cache_options.mode = "explicit"` with no cache breakpoints, so OpenAI may not create a cache. |
| `cache` | `mode = "implicit"` (automatic caching), plus a breakpoint after the static instructions (`openai_cache_instructions`), a fixed `prompt_cache_key`, and a 30-minute TTL. |

Both setups also send Portkey's `x-portkey-cache-force-refresh: true` header. **This mattered.** Portkey has its own response cache turned on for this key. The first time I repeated a document, Portkey answered with `x-portkey-cache-status: HIT` and the same `response_id` as before. It replayed an old answer and never called the model. With the refresh header, every call in this test returned `REFRESH`, which means a fresh model call.

### What the API sent back

Each call's `usage` block has exactly these fields: `input_tokens`, `input_tokens_details.cached_tokens`, `input_tokens_details.cache_write_tokens` (split by TTL), `output_tokens`, `output_tokens_details.reasoning_tokens`, and `total_tokens`.

| Check (from the API's own numbers) | `no_cache` | `cache` |
|---|---|---|
| Model calls with usage | 36 | 37 |
| Portkey cache status | all `REFRESH` | all `REFRESH` |
| Calls with `cached_tokens` > 0 | **0** | **37 of 37** |
| Calls with `cache_write_tokens` > 0 | **0** | 32 of 37 |
| `input_tokens` | 55,529 | 57,888 |
| `cached_tokens` (cache reads) | **0** | **49,042** |
| `cache_write_tokens` | **0** | 4,184 |
| Uncached input (input − cached − written) | 55,529 | 4,662 |
| `output_tokens` | 3,209 | 4,348 |
| ...of which `reasoning_tokens` | 1,134 | 1,945 |
| `total_tokens` | 58,738 | 62,236 |
| Share of input read from cache | 0.0% | **84.7%** |

**The `no_cache` run counts:** all 36 calls report `cached_tokens: 0` and `cache_write_tokens: 0`. The script checks this automatically and saves the result as `"checks": {"valid": true}` in `cache_test.json`.

**The `cache` setup worked:** every call read from the cache. A typical document looked like this:

| Call | `input_tokens` | `cached_tokens` | `cache_write_tokens` | `output_tokens` |
|---|---|---|---|---|
| 1 (read the document) | 1,366 | 1,224 | 16 | 25 |
| 2 (check the rules) | 1,507 | 1,240 | 141 | 65 |
| 3 (final answer) | 1,684 | 1,381 | 177 | 95 |

The 1,224 tokens read from cache on each first call are the instructions plus the tool definitions, which are identical for every document.

Seven calls (3 `no_cache`, 4 `cache`) returned HTTP 500 from the gateway and were retried automatically by the SDK. Those failed attempts have no `usage` block and cost nothing. They are listed in `cache_test.json` with `status_code: 500`.

## 2. Cost

**Prices per 1M tokens:** input $0.10, cached input $0.01, cache write $0.125, output $0.50.

**Formula per call:** cost = uncached × $0.10/1M + cached × $0.01/1M + written × $0.125/1M + output × $0.50/1M

| Cost part | `no_cache` | `cache` |
|---|---|---|
| Uncached input | 55,529 × $0.10/1M = $0.0055529 | 4,662 × $0.10/1M = $0.0004662 |
| Cached input | $0 | 49,042 × $0.01/1M = $0.0004904 |
| Cache write | $0 | 4,184 × $0.125/1M = $0.0005230 |
| Output | 3,209 × $0.50/1M = $0.0016045 | 4,348 × $0.50/1M = $0.0021740 |
| **Total, 12 documents** | **$0.0071574** | **$0.0036536** |
| **Cost per document** | **$0.00059645** | **$0.00030447** |

**Percent saved:**

```
Total:       ($0.0071574 − $0.0036536) ÷ $0.0071574 = 49.0% saved
Input only:  ($0.0055529 − $0.0014796) ÷ $0.0055529 = 73.4% saved
```

## 3. Comparison to the Problem 2 estimate

| | Problem 2 estimate | Real agent (this test) |
|---|---|---|
| What was measured | The handbook alone (10,058 tokens) on every call | The whole agent run: prompt, tools, document, tool results, output |
| Input tokens per model call | 10,058 | about 1,540 on average (1,365 to 1,975) |
| Model calls per document | 1 (assumed) | 3 (sometimes 4) |
| Uncached cost per call or document | $0.0010058 per call | $0.00059645 per document |
| Cost for 1,000, no cache | $1.0058 | $0.596 |
| Cost for 1,000, cache | $0.1017 | $0.304 |
| Savings from caching | 89.9% | 49.0% (73.4% on input alone) |

What changed:

1. **The real agent is cheaper than the estimate because the handbook is never sent.** The agent looks up only the vendor and SKU rows it needs through tools. A whole document (3 calls, about 4,600 input tokens) costs less than the handbook alone on one call. If the 10,058-token handbook were pasted into the prompt, each of the 3 calls would carry it: about 30,000 extra input tokens per document, or about $0.003 per document without caching. That is 5 times today's cost.
2. **The real savings are about half the estimate.** Problem 2 assumed every token was cached input. In reality:
   - output tokens (5 times the input price) get no discount;
   - each call adds new tokens (tool results) that are written to the cache at 1.25 times the input price;
   - only the shared prefix is ever a cache hit.

## 4. Projection: 1,000 documents a day for 30 days (30,000 documents)

| Setup | Per document | Per day (1,000) | 30 days (30,000) |
|---|---|---|---|
| `no_cache` | $0.00059645 | $0.596 | **$17.89** |
| `cache` | $0.00030447 | $0.304 | **$9.13** |
| Saved | $0.00029198 | $0.292 | **$8.76 (49%)** |

The cache run happened to produce more output tokens (see the next section). If both setups had the same output as the `no_cache` run, the cached setup would cost $0.000257 per document, which is **$7.71 for 30 days, a 57% saving**. A fair range for the monthly saving is **$8.76 to $10.18**.

Even at 30,000 documents, the agent costs less than $18 a month without caching. Caching is worth turning on because it is free to do, but at this size it changes dollars, not the budget.

## 5. Surprising numbers, and why they happen

1. **Portkey replayed old answers.** Repeating a document returned the same `response_id` with `x-portkey-cache-status: HIT`, and the reported token counts were copies of the first call's. Portkey's gateway response cache sits in front of the model, so a "run" can cost nothing and not touch the model at all. A naive no-cache test would have measured replays. Every call in this test forced a refresh to avoid that.
2. **The very first call of the `cache` run was already a cache hit** (p01: 1,239 cached tokens). A short probe I ran a few minutes earlier had warmed the cache, and the TTL is 30 minutes. OpenAI's cache is shared across runs, not per script.
3. **Cache writes cost more than cache reads.** 4,184 written tokens cost $0.000523, while 49,042 read tokens cost $0.000490. Each call writes its new suffix (the latest tool result) at 1.25 times the input price, and that suffix is never reused by the next document.
4. **The cached run produced 35% more output tokens** (4,348 vs 3,209). That came almost entirely from reasoning tokens, not from caching. Two documents made the model reason much longer this time: p09 used 893 reasoning tokens on its last call (vs 88 before), and p12 used 422 (vs 20). Output costs 5 times as much as input, so this noise ate about $0.0006 of the savings. Output length differs from run to run even with identical input.
5. **The cacheable prefix is barely over the minimum.** Prompt caching only starts at about 1,024 tokens. The static instructions and tools are about 1,224 tokens, so the first call of each document caches 1,224 of its 1,366 tokens. If the prompt were shortened by about 200 tokens, the first call of each document would stop caching completely.
6. **The handbook estimate was wrong in the "good" direction.** The cost driver is not document size but the number of model calls and how much each call re-sends. Each call re-sends everything before it, so input grows 1,366 → 1,507 → 1,684 within one document.
7. **Seven HTTP 500 errors** came back from the gateway and were retried automatically. They didn't change the results or the cost, but they would matter at 1,000 documents a day.
