# HW6: Campus Customs Vendor Desk Agent

An AI agent that reads one vendor document (an HTML quote, a PDF quote, or an `.eml` email), pulls out the vendor, SKU, unit price, lead time, and minimum order, and recommends or rejects the quote using the shop handbook's four purchasing rules. It runs on `gpt-6-luna` through Portkey, built with PydanticAI.

**Results page:** open [`output/hw6_report.html`](output/hw6_report.html). It is one file and needs no internet connection.

## How to run the agent

1. Install Python 3.13 or newer, then create a virtual environment and install the requirements. If the folder is inside OneDrive or Dropbox, pause syncing first.

   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set your Portkey key. Never commit `.env`.

   ```bash
   copy .env.example .env          # macOS/Linux: cp .env.example .env
   ```

   ```
   PORTKEY_API_KEY=your-portkey-api-key-here
   OPENAI_MODEL=gpt-6-luna
   ```

3. Run the agent on a document in `data/`:

   ```bash
   python agent.py p01_bluehen_quote.html                  # one document, all defenses on
   python agent.py --practice                              # all 12 practice documents
   python agent.py exam_docs/e01_quote.html                # an exam document
   python agent.py --practice --defenses none              # the undefended agent (Problem 3 version)
   python agent.py p06_qtextile_quote.pdf --defenses code,prompt   # pick layers
   ```

Each run prints a JSON answer and appends to `output/usage_log.json` (tokens and cost) and `output/audit_trail.json` (every tool call plus the final answer). The trap tools `send_email` and `approve_payment` log to `output/trap_calls.json`.

## Rebuild the results

| Problem | Command | Output |
|---|---|---|
| 2 Size up the handbook | `python count_tokens.py` | `output/handbook_estimate.md` |
| 4 Cache test | `python cache_test.py` | `output/cache_test.json`, `output/cache_test.md` |
| 5 Attack your own agent | `python attack_test.py` | `output/attack_results.json`, `output/attack_results.md` |
| 6 Defenses | `python defense_test.py --layers none code design prompt all` | `output/defense_results.json`, `output/defense_results.md` |
| 7 Red team | `python make_attacks.py` then `python red_team_test.py` | `data/my_attacks/`, `output/red_team.json`, `output/red_team.md` |
| 8 Exam | `python exam_test.py` | `output/exam_results.json` |
| 9 Results page | `python make_report.py` | `output/hw6_report.html` |

## Files

| File | What it does |
|---|---|
| `agent.py` | Builds and runs the agent, with switchable defenses and logging |
| `tools.py` | Document reader, handbook lookups, the purchasing-rules check, and the two trap tools |
| `models.py` | `VendorDecision`, the structured answer |
| `defenses.py` | The code, design, and prompt defense layers |
| `prompts/prompt.md` | The defended prompt (`prompt_baseline.md` is the undefended one) |
| `config.py` | Portkey client; locks the model to `gpt-6-luna` |
| `data/` | Handbook, prices, practice and exam documents, answer key, red-team attacks |
| `output/` | All results, write-ups, and `harness.md`, which explains the fields, tools, and safety design |
| `AI_Prompt.md` | The assignment text for each problem, with status notes |
