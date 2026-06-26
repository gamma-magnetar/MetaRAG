# Cashfree Ops RAG — text-to-SQL assistant

A small, modular Retrieval-Augmented-Generation system that writes **read-only Redshift SQL**
for the ops team. It is grounded in a **registry** (your structured source of truth — schema,
joins, rules, dictionaries, golden queries), retrieves the relevant pieces for each question,
asks Gemini to write the SQL, and **validates** the result (read-only, date-bound, known tables).

It ships seeded with your real data: **44 verified tables**, the join map, the ops rules, the
product / reg-key / status dictionaries, and **5 golden queries** (including the GMV roll-up).

> It runs **without any API key** in keyword-retrieval mode (great for trying it out). Add a
> Gemini key to turn on embeddings + SQL generation.

---

## 1. Setup (VS Code)

```bash
# from the project folder
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                 # then (optional) paste your GEMINI_API_KEY into .env

python rag.py index                  # build the search index from the registry
```

In VS Code: **Open Folder** → this directory, then pick the `.venv` interpreter
(Ctrl/Cmd-Shift-P → "Python: Select Interpreter"). Open a terminal and run the commands above.

Get a Gemini key at <https://aistudio.google.com/apikey> and put it in `.env`:
`GEMINI_API_KEY=...`. **Re-run `python rag.py index`** after adding the key so the index uses
real embeddings.

---

## 2. Use it

```bash
python rag.py search "how much GMV did this merchant do on credit cards"   # retrieval only (no key needed)
python rag.py ask    "unsettled amount for merchant 12345"                 # generate SQL (needs key)
python rag.py chat                                                         # interactive loop
python rag.py eval                                                         # retrieval regression over golden queries
python rag.py render-databook                                              # regenerate outputs/DATABOOK.md
python rag.py -h                                                           # all commands
```

`ask` prints the SQL, then validation (✓ / warnings / errors) and the tables it used.
`search` is the best way to see *why* the model got the context it did.

---

## 3. The self-updating part — adding a table

This is the automated version of the manual flow we used for the GMV table.

**With live Redshift** (set `REDSHIFT_*` in `.env`, read-only user, `pip install redshift-connector`):
```bash
python rag.py add-table cfanalytics merchant_gmv_master_data_base --note "Canonical GMV source; key=mid"
# -> pulls real columns from svv_columns, writes the card to registry/tables.yaml
```

**Without Redshift** (paste the columns; types are semicolon-separated so commas in
`numeric(18,2)` are safe):
```bash
python rag.py add-table cfsellers transactionrefunds \
  --note "Refund ledger" \
  --columns "id:bigint; cftxnid:character varying(60); refundamount:numeric(18,2); refundstatus:character varying(40); addedon:timestamp"
```

Then review and apply:
```bash
git diff registry/tables.yaml          # your "approval" step
python rag.py render-databook          # regenerate the DATABOOK
python rag.py index                    # re-index so the bot can retrieve it
```

That's the loop: **edit the registry → DATABOOK + index regenerate.** The DATABOOK is generated
output, not the master.

---

## 4. What's in here (file map)

```
registry/              ← L0 SOURCE OF TRUTH (edit these; everything else is derived)
  tables.yaml            44 verified tables: schema, columns+types, key columns, notes
  joins.yaml             join edges + caveats (incl. the cftxnid join-key warning)
  rules.yaml             the ops rules (Redshift-only, timeout trap, ROUTER, fan-out, …)
  glossary.yaml          business definitions (fully-activated, CTS/FTS, unsettled, …)
  dictionaries.yaml      product codes, product ids, status codes, 247 reg-keys, COALESCE groups
  golden_queries.yaml    validated question → SQL examples (your best accuracy lever)

app/
  config.py              settings (config.yaml + .env)
  registry.py            L0   load / save the registry
  corpus.py              L2   registry → retrieval documents (+ tokenizer)
  embeddings.py          L2   Embedder: Gemini (default) or offline hashing fallback
  store.py               L2   local dense + BM25 index (persist / load)
  retriever.py           L3   hybrid search + RRF + type-aware context budgeting
  prompt.py              L4   assemble system + context + few-shot examples
  llm.py                 L4   Gemini SQL generation (NullLLM when no key)
  guardrails.py          L5   validate SQL: read-only, date-bound, known tables
  redshift.py            L1/L5  optional live Redshift: introspection + EXPLAIN
  ingest.py              L1   self-updating: add / replace a table card
  databook.py            L0→docs  render the registry to DATABOOK.md
  pipeline.py            L3–L5  the ask flow: retrieve → generate → validate
  cli.py                 the commands

config.yaml              models (verify names!), retrieval params, paths
rag.py                   entrypoint:  python rag.py <command>
data/index/              built index (gitignored)
outputs/DATABOOK.md      generated doc (the file you'd upload to the Gem)
tests/                   guardrail sanity tests:  python tests/test_guardrails.py
```

These layers map 1:1 to the architecture deck, so swapping a piece later (e.g. the local store
for **pgvector / Qdrant**, or Gemini for **Vertex AI RAG Engine**) only touches that one module.

---

## 5. Notes & next steps

- **Models:** `config.yaml` pins `gemini-embedding-001` and `gemini-2.5-flash` — confirm those are
  current for your account and adjust if needed.
- **Offline mode:** without a key, dense embeddings use a deterministic hashing fallback; BM25 does
  the heavy lifting for schema lookups. Add a key + re-index for full semantic retrieval.
- **EXPLAIN validation:** `python rag.py ask "…" --explain` dry-runs the SQL against Redshift if
  `REDSHIFT_*` is configured (read-only, no execution).
- **Hosting later:** wrap `pipeline.answer_question` in a small **Cloud Run** service (chat/API or a
  Slack app), keep secrets in **Secret Manager**, and move the index to **Cloud SQL + pgvector** or
  **Gemini File Search** when you outgrow the local store. The registry stays the source of truth, so
  none of that is a rewrite.
- **Security:** never commit `.env`; always use a **read-only** Redshift role; for text-to-SQL you
  send *schema + the question* to the model, not raw rows — confirm that's acceptable for your data
  policy (or keep it in-VPC with Vertex / self-hosted embeddings).
```
