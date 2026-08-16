from __future__ import annotations

import json

import requests

from catalog.db import get_connection, get_or_create_taxonomy_path, init_schema
from config import CATEGORIES, HF_DATASET, SAMPLE_PER_CATEGORY


def _jsonl_url(category: str) -> str:
    return f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main/raw/meta_categories/meta_{category}.jsonl"


def _stream_rows(category: str):
    """Stream a category's metadata JSONL line-by-line, parsing each line independently.

    Avoids pyarrow-based JSON readers, which infer one schema for the whole file and
    error out when a freeform nested field (e.g. `details.*`) changes type mid-file.
    """
    with requests.get(_jsonl_url(category), stream=True, timeout=60) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _to_float(value):
    try:
        if value is None or value == "None" or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    f = _to_float(value)
    return int(f) if f is not None else None


def _breadcrumb_for(row, category: str) -> list[str]:
    cats = row.get("categories")
    if cats and len(cats) > 0:
        return list(cats)
    main = (row.get("main_category") or "").strip()
    return [main] if main else [category.replace("_", " ")]


def ingest_category(conn, category: str) -> int:
    inserted = 0
    rows = _stream_rows(category)
    try:
        for row in rows:
            if inserted >= SAMPLE_PER_CATEGORY:
                break

            title = (row.get("title") or "").strip()
            if not title:
                continue

            breadcrumb = _breadcrumb_for(row, category)
            taxonomy_id = get_or_create_taxonomy_path(conn, breadcrumb)

            conn.execute(
                """
                INSERT OR IGNORE INTO items
                    (parent_asin, title, description, features, price, store,
                     main_category, average_rating, rating_number, taxonomy_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("parent_asin"),
                    title,
                    json.dumps(row.get("description") or []),
                    json.dumps(row.get("features") or []),
                    _to_float(row.get("price")),
                    row.get("store"),
                    row.get("main_category"),
                    _to_float(row.get("average_rating")),
                    _to_int(row.get("rating_number")),
                    taxonomy_id,
                ),
            )
            inserted += 1
    finally:
        rows.close()
    conn.commit()
    return inserted


def main():
    conn = get_connection()
    init_schema(conn)

    total = 0
    for category in CATEGORIES:
        count = ingest_category(conn, category)
        total += count
        print(f"{category}: {count} items")

    print(f"\nTotal items ingested: {total}")

    taxonomy_count = conn.execute("SELECT COUNT(*) FROM taxonomy").fetchone()[0]
    print(f"Total taxonomy nodes: {taxonomy_count}")

    print("\nSample breadcrumbs:")
    samples = conn.execute(
        """
        SELECT i.title, t.id FROM items i JOIN taxonomy t ON i.taxonomy_id = t.id
        ORDER BY RANDOM() LIMIT 8
        """
    ).fetchall()
    for title, leaf_id in samples:
        path = []
        node_id = leaf_id
        while node_id is not None:
            name, parent_id = conn.execute(
                "SELECT name, parent_id FROM taxonomy WHERE id = ?", (node_id,)
            ).fetchone()
            path.append(name)
            node_id = parent_id
        print(f"  {' > '.join(reversed(path))}  ::  {title[:60]}")

    conn.close()


if __name__ == "__main__":
    main()
