# Personalized Autosuggest Framework

A personalized autosuggest system: a text/demographics-aware suggestion API over a real product catalog, which learns from user selections over time. See [Plan.MD](Plan.MD) for the full phased roadmap.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Catalog ingestion (Phase 1)

```bash
python -m catalog.ingest
```

Streams product metadata for all 33 [Amazon Reviews 2023](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) categories (McAuley-Lab, Hugging Face) directly over HTTP as JSONL — bypassing `datasets`/pyarrow's JSON loader, which errors on this dataset's inconsistent nested field types — and writes a capped sample per category into `data/catalog.db` (SQLite, gitignored).

Current ingested catalog: **24,640 items**, **8,884 taxonomy nodes**.

## Candidate generation with Solr (Phase 2)

Solr is the **candidate generator**: given partial query text, it returns the top-N matching items by relevance. It does *not* do personalization or ranking-model scoring — that's a separate, app-layer step planned for Phase 4/5 (see [Plan.MD](Plan.MD)). Solr's job here is just fast, relevant prefix/text matching over `title` and the flattened `taxonomy_path` for every item.

**Run Solr** (via Docker):

```bash
docker run -d --name solr-autosuggest -p 8983:8983 solr:9 solr-precreate items
```

**Set up the schema and index the catalog:**

```bash
source .venv/bin/activate
python -m catalog.solr_schema   # adds the title/taxonomy_path/store/price/rating fields + a prefix-matching field type
python -m catalog.index_solr    # pushes all items from data/catalog.db into Solr
```

The `title` field uses a custom `text_prefix` field type (edge n-grams at index time, e.g. `hammock` → `ha`, `ham`, `hamm`, ...) so a partial query like `hamm` matches `Hammock` — this is what makes it behave like autosuggest rather than plain full-text search.

**Query it:**

```bash
python -m catalog.suggest "wireless headph"
```

or hit Solr directly:

```bash
curl -s "http://localhost:8983/solr/items/select" \
  --get \
  --data-urlencode "q=title:guitar" \
  --data-urlencode "defType=edismax" \
  --data-urlencode "qf=title^2 taxonomy_path" \
  --data-urlencode "rows=5" \
  --data-urlencode "fl=title,taxonomy_path,score" | python3 -m json.tool
```

or browse `http://localhost:8983/solr/#/items/query` in the browser for an interactive query UI.

## Synthetic demographic-preference bootstrap (Phase 3)

The real catalog has no user demographics or interaction history, so before a ranking
model can be trained there's nothing to train it *on*. This phase manufactures a clearly
labeled synthetic dataset — synthetic users, a demographic → taxonomy-affinity prior, and
simulated suggest/select events consistent with that prior — to give Phase 4's ranker a
non-trivial cold-start signal. It's a bootstrap, not real user data: `users.is_synthetic`
and `events.source = 'synthetic'` mark it as such, and it's fully superseded by real
events once Phase 6's feedback loop has enough volume.

```bash
source .venv/bin/activate
python -m bootstrap.generate
```

This is idempotent — rerunning replaces all synthetic users/affinity/events rather than
accumulating them. It:

- Defines a minimal demographic schema — `age_bracket` × `gender` × `region` — where each
  combination is a "segment" (`config.py`)
- Builds a `demographic_affinity` table: each segment gets a weight over every top-level
  taxonomy root, derived by matching root names into ~9 interest clusters (electronics,
  fashion & beauty, home & living, family, media, health & grocery, sports/outdoors/auto,
  hobbies & crafts, gifts) and applying illustrative per-age/gender/region bias vectors
  through a softmax (`bootstrap/affinity.py`) — these biases are placeholders to make the
  bootstrap data non-trivial, not claims about real demographic behavior
- Generates synthetic `users` with random demographics (`bootstrap/users.py`)
- Simulates suggest/select sessions per user, sampling a taxonomy branch by that user's
  segment affinity, then an item from it, then a partial-typing query prefix from its
  title — writing `suggest` events always and paired `select` events with configurable
  probability (`bootstrap/events.py`)

## Schema

**`items`** — one row per product

```sql
CREATE TABLE items (
    parent_asin TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,              -- JSON-encoded list of strings
    features TEXT,                 -- JSON-encoded list of strings
    price REAL,
    store TEXT,
    main_category TEXT,
    average_rating REAL,
    rating_number INTEGER,
    taxonomy_id INTEGER REFERENCES taxonomy(id)   -- leaf node this item belongs to
);
```

**`taxonomy`** — category tree, one row per node; an item's full breadcrumb is the chain of `parent_id` links from its `taxonomy_id` up to a row with `parent_id IS NULL`

```sql
CREATE TABLE taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES taxonomy(id),
    depth INTEGER NOT NULL,
    UNIQUE(name, parent_id)
);
```

When the source data has a real category breadcrumb (e.g. most of `Electronics`), the item gets a multi-level path. When it doesn't (e.g. most of `All_Beauty`, `Digital_Music`), it falls back to a single-level node from `main_category`.

**`users`**, **`demographic_affinity`**, **`events`** — added in Phase 3, populated with synthetic data for now (see above)

```sql
CREATE TABLE users (
    user_id TEXT PRIMARY KEY,
    age_bracket TEXT NOT NULL,
    gender TEXT NOT NULL,
    region TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE demographic_affinity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    age_bracket TEXT NOT NULL,
    gender TEXT NOT NULL,
    region TEXT NOT NULL,
    taxonomy_root_id INTEGER NOT NULL REFERENCES taxonomy(id),
    weight REAL NOT NULL,
    UNIQUE(age_bracket, gender, region, taxonomy_root_id)
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    event_type TEXT NOT NULL CHECK(event_type IN ('suggest', 'select')),
    query_text TEXT NOT NULL,
    parent_asin TEXT REFERENCES items(parent_asin),   -- set for 'select', NULL for 'suggest'
    source TEXT NOT NULL DEFAULT 'real' CHECK(source IN ('real', 'synthetic')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

`events` doubles as the log for Phase 5's `/suggest` and `/select` API calls, tagged `source = 'real'` — the same shape as the synthetic bootstrap data so Phase 4's training pipeline doesn't need to special-case either one.

## Sample data

| title | store | price | rating | taxonomy path |
|---|---|---|---|---|
| Cat Window Perch Durable Cat Hammock Seat for Indoor Cats... | Mewoo | $23.99 | 4.4 (130) | `Pet Supplies > Cats > Beds & Furniture > Hammocks` |
| Ryan & Rose Cutie Tensils Baby Spoon and Fork [2 Pack] (Ballet) | Ryan & Rose | $11.99 | 4.6 (2294) | `Baby Products > Feeding > Solid Feeding > Utensils > Flatware Sets` |
| Dodo Babies 5-Pack Baby Burp Cloths... | Dodo Babies | $16.95 | 4.7 (8394) | `Baby Products > Feeding > Bibs & Burp Cloths > Burp Cloths` |
| Hot Topic Gift Card | Hot Topic | $25.00 | 4.8 (3414) | `Gift Cards > Gift Cards: Non-Amazon Branded` |
| Somewhere in Time | — | — | — | `CDs & Vinyl > Soundtracks > Movie Scores` |
| Anti-Fog Lens Wipe Cloth Reusable Eyeglasses Tablets Microfiber | — | — | — | `Health & Personal Care` *(flat fallback — no source breadcrumb)* |
