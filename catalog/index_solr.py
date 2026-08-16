from __future__ import annotations

import requests

from catalog.db import get_connection, taxonomy_path
from catalog.solr_schema import ensure_schema
from config import SOLR_CORE, SOLR_URL

BATCH_SIZE = 500


def _doc(row, path: str) -> dict:
    return {
        "id": row["parent_asin"],
        "title": row["title"],
        "taxonomy_path": path,
        "store": row["store"],
        "main_category": row["main_category"],
        "price": row["price"],
        "average_rating": row["average_rating"],
        "rating_number": row["rating_number"],
    }


def index_all() -> int:
    ensure_schema()

    conn = get_connection()
    conn.row_factory = None
    cur = conn.execute(
        """
        SELECT parent_asin, title, store, main_category, price,
               average_rating, rating_number, taxonomy_id
        FROM items
        """
    )
    columns = [d[0] for d in cur.description]

    batch = []
    total = 0
    for values in cur:
        row = dict(zip(columns, values))
        path = " > ".join(taxonomy_path(conn, row["taxonomy_id"]))
        batch.append(_doc(row, path))
        if len(batch) >= BATCH_SIZE:
            _push(batch)
            total += len(batch)
            batch = []
    if batch:
        _push(batch)
        total += len(batch)

    requests.get(f"{SOLR_URL}/{SOLR_CORE}/update", params={"commit": "true"}).raise_for_status()
    conn.close()
    return total


def _push(docs: list[dict]) -> None:
    resp = requests.post(f"{SOLR_URL}/{SOLR_CORE}/update/json/docs", json=docs)
    resp.raise_for_status()


if __name__ == "__main__":
    count = index_all()
    print(f"Indexed {count} items into Solr core '{SOLR_CORE}'.")
