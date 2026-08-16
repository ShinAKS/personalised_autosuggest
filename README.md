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
