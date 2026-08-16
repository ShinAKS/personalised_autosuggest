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

## Sample data

| title | store | price | rating | taxonomy path |
|---|---|---|---|---|
| Cat Window Perch Durable Cat Hammock Seat for Indoor Cats... | Mewoo | $23.99 | 4.4 (130) | `Pet Supplies > Cats > Beds & Furniture > Hammocks` |
| Ryan & Rose Cutie Tensils Baby Spoon and Fork [2 Pack] (Ballet) | Ryan & Rose | $11.99 | 4.6 (2294) | `Baby Products > Feeding > Solid Feeding > Utensils > Flatware Sets` |
| Dodo Babies 5-Pack Baby Burp Cloths... | Dodo Babies | $16.95 | 4.7 (8394) | `Baby Products > Feeding > Bibs & Burp Cloths > Burp Cloths` |
| Hot Topic Gift Card | Hot Topic | $25.00 | 4.8 (3414) | `Gift Cards > Gift Cards: Non-Amazon Branded` |
| Somewhere in Time | — | — | — | `CDs & Vinyl > Soundtracks > Movie Scores` |
| Anti-Fog Lens Wipe Cloth Reusable Eyeglasses Tablets Microfiber | — | — | — | `Health & Personal Care` *(flat fallback — no source breadcrumb)* |
