# Handbook Size and Cost Estimate

**File:** `data/shop_handbook.md`
**Model:** `gpt-6-luna`
**Prices:** `data/prices.json`

## 1. Token count

| Measure | Value |
|---|---|
| Characters | 28,903 |
| Words | 6,127 |
| **Tokens** | **10,058** |
| Characters per token | 2.87 |

### How I got it

I counted the tokens with OpenAI's `tiktoken` library and the `o200k_base` encoding, the tokenizer used by current OpenAI GPT models. The script is `count_tokens.py`:

```python
text = Path("data/shop_handbook.md").read_text(encoding="utf-8")
enc = tiktoken.get_encoding("o200k_base")
tokens = enc.encode(text)
print(len(tokens))   # 10,058
```

Notes:

- The handbook runs at about 2.9 characters per token, well below the usual rule of thumb of about 4 for plain English. Most of the file is tables of SKUs, dollar amounts, and `|` separators, which split into many small tokens. A "characters ÷ 4" estimate would give about 7,226 tokens, roughly 28% too low.
- 10,058 is the handbook text only. A real API call also adds a few tokens of message formatting, plus the system prompt, the vendor document, and the model's output. Those costs are not included here.

## 2. Prices for `gpt-6-luna` (from `prices.json`)

| Token type | Price per 1M tokens | Price per token |
|---|---|---|
| Input (uncached) | $0.10 | $0.0000001 |
| Cached input (cache read) | $0.01 | $0.00000001 |
| Cache write | $0.125 | $0.000000125 |
| Output | $0.50 | $0.0000005 |

Formula: **cost = tokens × (price per 1M ÷ 1,000,000)**

## 3. Cost of the handbook on one call

**Without caching:** the handbook is billed as normal input.

```
10,058 × $0.10 / 1,000,000 = $0.0010058   ≈ $0.0010 (about 1/10 of a cent)
```

**With caching:** this depends on whether the handbook is already in the cache.

- First call (cache write):

  ```
  10,058 × $0.125 / 1,000,000 = $0.00125725 ≈ $0.0013
  ```

- Any later call (cache read):

  ```
  10,058 × $0.01 / 1,000,000 = $0.00010058 ≈ $0.0001 (about 1/100 of a cent)
  ```

A single call with caching costs more than without it ($0.00126 vs. $0.00101), because writing to the cache costs 25% more than normal input. Caching only pays off when the handbook is reused.

## 4. Cost of the handbook on 1,000 calls

**Without caching:** all 1,000 calls pay full input price.

```
1,000 × 10,058 = 10,058,000 tokens
10,058,000 × $0.10 / 1,000,000 = $1.0058   ≈ $1.01
```

**With caching:** one cache write, then 999 cache reads.

```
Cache write:  1 × 10,058 × $0.125 / 1,000,000 = $0.00125725
Cache reads: 999 × 10,058 × $0.01  / 1,000,000 = 10,047,942 × $0.00000001 = $0.10047942
Total                                          = $0.10173667  ≈ $0.10
```

If all 1,000 calls were billed at the cached rate, ignoring the one-time write, the total would be 10,058,000 × $0.01 / 1,000,000 = $1.0058 ÷ 10 = **$0.10058**. The cache write adds only about $0.0012 on top of that.

## 5. Summary

| Scenario | Handbook tokens | Cost |
|---|---|---|
| 1 call, no caching | 10,058 | **$0.0010058** |
| 1 call, cache write (first call) | 10,058 | **$0.00125725** |
| 1 call, cache read (later calls) | 10,058 | **$0.00010058** |
| 1,000 calls, no caching | 10,058,000 | **$1.0058** |
| 1,000 calls, with caching (1 write + 999 reads) | 10,058,000 | **$0.1017** |

**Savings from caching over 1,000 calls:**

```
$1.0058 − $0.1017 = $0.9041 saved
$0.9041 ÷ $1.0058 ≈ 89.9% less
```

Cached reads cost one tenth of the normal input price, so caching cuts the handbook's cost by about 90%.

**Assumption:** the 1,000 calls stay within the cache's lifetime, so the handbook is written once. If the cache expires between batches, each new batch pays one more write of $0.00125725. That changes the total very little.
