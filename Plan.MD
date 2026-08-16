# Personalized Autosuggest Framework — Roadmap

## Context

Building a personalized autosuggest system from scratch (empty repo). Three requirements drive the design:
1. A model trained on user preferences × demographics
2. An API that takes `{user_text, demographics}` and returns ranked catalog suggestions
3. A feedback loop where user selections personalize future suggestions

Catalog/taxonomy source : **Amazon Reviews 2023** (McAuley-Lab, Hugging Face) — item metadata includes a hierarchical `categories` field (breadcrumb taxonomy) alongside `title`, `description`, `features`, `price`, `store`. Scope : sample a small slice from **all 33 category configs** (`raw_meta_<CATEGORY>`) to get full taxonomy breadth immediately, capping per-category item count so ingestion stays fast (e.g. ~500–1,000 items/category → ~20-30k items total).

Known gap: the dataset has no user demographics (privacy-scrubbed). So step 1 ("train on preferences × demographics") can't be trained on real Amazon interaction data — we bootstrap with a synthesized demographic-affinity dataset, then let the real feedback loop (step 6 below) take over as actual usage accumulates.

This is a staged build — each phase produces something runnable before the next begins, rather than building all components in isolation and integrating at the end.

## Tech Stack

- Python, `datasets` (HF) for ingestion, SQLite for local storage (items, taxonomy, users, events) — easy to swap for Postgres later
- FastAPI + uvicorn for the API
- **Solr** for candidate generation (prefix/text match over item title + taxonomy path), replacing the earlier SQLite FTS5 plan — SQLite remains the source-of-truth store for items/taxonomy/users/events, Solr is a query-time index built from it
- scikit-learn / LightGBM for the ranking model (tabular features, not deep two-tower — appropriate at this data scale)

**Decision on Solr's role**: Solr's Learning-to-Rank (LTR) plugin can accept a model directly as a query param (`rq={!ltr model=... efi.*=...}`), but that requires converting the model to Solr's supported format (linear/LambdaMART) and re-defining every feature in Solr's own feature-store DSL — duplicated effort at a stage where the feature set is still changing. Solr is scoped to **candidate generation only**; ranking stays in the app layer (Phase 4/5) so the model can be trained/iterated on freely with LightGBM directly. Revisit Solr LTR later only if the extra network hop between candidate gen and rerank becomes a measured latency problem.

## Phase 0 — Repo scaffold
- `pyproject.toml`/`requirements.txt`, package layout: `catalog/`, `api/`, `models/`, `data/` (gitignored cache dir)
- Config module for dataset category list, sample size per category, DB path

## Phase 1 — Catalog + taxonomy ingestion
- Script (`catalog/ingest.py`) that loads `raw_meta_<CATEGORY>` for each of the 33 configs via `datasets.load_dataset(..., split="full")`, takes a capped random sample per category, and normalizes fields: `parent_asin`, `title`, `description`, `features`, `price`, `store`, `categories` (breadcrumb list), `main_category`
- Build a `taxonomy` table from the union of all `categories` breadcrumbs (parent/child edges, deduped) and an `items` table (item → leaf taxonomy node)
- Load into SQLite; sanity-check counts and a few sample breadcrumbs per category

## Phase 2 — Candidate generation (non-personalized autosuggest, working end-to-end)
- Run Solr locally (single core, e.g. `items`), define a schema covering `parent_asin`, `title` (text field with edge n-gram/suggester analysis for prefix match), taxonomy path text, `store`, `average_rating`, `price`
- `catalog/index_solr.py`: reads items from SQLite (Phase 1's output) and pushes them into the Solr core via its update API
- `catalog/suggest.py`: given a text prefix/query, hit Solr's query endpoint and return top-N matching items ranked by Solr's relevance score (+ rating as tiebreak)
- This phase's output is a working, non-personalized suggest function — validates the data pipeline before any ML is added

## Phase 3 — Synthetic demographic-preference bootstrap dataset
- Define a small demographic schema (age bracket, gender, region — kept minimal/extensible)
- Generate synthetic users + synthetic (demographic → taxonomy-category affinity) weights, then simulate synthetic query/select events consistent with those affinities over the real catalog
- This is clearly labeled as a bootstrap/cold-start dataset, not real user data — used only to give the ranking model a non-trivial prior before real events exist

## Phase 4 — Ranking model (v1)
- Features per (query, candidate item, user demographics): text-match score, taxonomy-affinity score for the user's demographic segment, item popularity/rating, price bucket
- Train a LightGBM/GBM ranker on the Phase 3 synthetic events
- `models/rank.py`: loads model, re-ranks Phase 2's candidate list

## Phase 5 — API
- FastAPI service (`api/main.py`):
  - `POST /suggest {text, user_id, demographics}` → candidate gen (Phase 2, Solr query) → re-rank (Phase 4 model, applied in the app layer using stored or passed demographics) → ranked items
  - `POST /select {user_id, query, item_id}` → logs the event (Phase 6)
- `user_id` demographics stored in a `users` table on first sight (or passed each call, cached)

## Phase 6 — Personalization feedback loop
- `events` table logs every suggest + select
- Per-user taxonomy-affinity cache updated (decayed counts) on each `/select`, read by the ranker as an extra feature at request time → gives immediate personalization without waiting for retraining
- Periodic batch retrain job (`models/retrain.py`) that re-trains the Phase 4 ranker on accumulated real events, gradually diluting reliance on the synthetic bootstrap data as real volume grows

## Phase 7 — Verification
- Ingest a couple of categories, confirm taxonomy/item counts look right
- Run API locally; `curl /suggest` for a prefix, confirm reasonable non-personalized results (validates Phase 2/5)
- Simulate a user issuing several `/select` events toward one taxonomy branch, then re-query the same prefix and confirm ranking shifts toward that branch (validates Phase 6)
- Basic unit tests for taxonomy parsing and the Solr query-building function
