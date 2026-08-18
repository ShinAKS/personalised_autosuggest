from __future__ import annotations

import random
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

from catalog.db import taxonomy_roots
from config import SESSIONS_PER_USER_RANGE, SYNTHETIC_SELECT_PROBABILITY

EVENT_SPREAD_DAYS = 90  # events are backdated uniformly over this window


def _items_by_root(conn: sqlite3.Connection) -> dict[int, list[tuple[str, str]]]:
    """Maps each taxonomy root id to the (parent_asin, title) of items beneath it."""
    root_of = taxonomy_roots(conn)
    by_root: dict[int, list[tuple[str, str]]] = defaultdict(list)
    rows = conn.execute("SELECT parent_asin, title, taxonomy_id FROM items WHERE taxonomy_id IS NOT NULL")
    for parent_asin, title, taxonomy_id in rows:
        root_id = root_of.get(taxonomy_id)
        if root_id is not None:
            by_root[root_id].append((parent_asin, title))
    return by_root


def _load_affinity_by_segment(conn: sqlite3.Connection) -> dict[tuple[str, str, str], dict[int, float]]:
    by_segment: dict[tuple[str, str, str], dict[int, float]] = defaultdict(dict)
    rows = conn.execute("SELECT age_bracket, gender, region, taxonomy_root_id, weight FROM demographic_affinity")
    for age, gender, region, root_id, weight in rows:
        by_segment[(age, gender, region)][root_id] = weight
    return by_segment


def _simulate_query(title: str, rng: random.Random) -> str:
    """A plausible partial-typing prefix of an item title, e.g. 'Cat Window Per'."""
    words = title.split()
    prefix = " ".join(words[: rng.randint(1, min(3, len(words)))])
    if len(prefix) > 4 and rng.random() < 0.5:
        prefix = prefix[: rng.randint(3, len(prefix))]
    return prefix.strip()


def _random_timestamp(rng: random.Random) -> datetime:
    delta = timedelta(days=rng.uniform(0, EVENT_SPREAD_DAYS), seconds=rng.randint(0, 86_400))
    return datetime.utcnow() - delta


def simulate_events(
    conn: sqlite3.Connection,
    users: list[tuple[str, str, str, str]],
    rng: random.Random,
) -> tuple[int, int]:
    """Simulates suggest/select sessions per user, biased by their segment's taxonomy
    affinity. Returns (suggest_count, select_count). Replaces any prior synthetic events."""
    affinity_by_segment = _load_affinity_by_segment(conn)
    by_root = _items_by_root(conn)

    conn.execute("DELETE FROM events WHERE source = 'synthetic'")

    rows = []
    for user_id, age, gender, region in users:
        roots, weights = [], []
        for root_id, weight in affinity_by_segment[(age, gender, region)].items():
            if root_id in by_root:
                roots.append(root_id)
                weights.append(weight)
        if not roots:
            continue

        for _ in range(rng.randint(*SESSIONS_PER_USER_RANGE)):
            root_id = rng.choices(roots, weights=weights, k=1)[0]
            parent_asin, title = rng.choice(by_root[root_id])
            query_text = _simulate_query(title, rng)
            suggest_ts = _random_timestamp(rng)

            rows.append((user_id, "suggest", query_text, None, "synthetic", suggest_ts.isoformat(sep=" ")))
            if rng.random() < SYNTHETIC_SELECT_PROBABILITY:
                select_ts = suggest_ts + timedelta(seconds=rng.randint(2, 25))
                rows.append(
                    (user_id, "select", query_text, parent_asin, "synthetic", select_ts.isoformat(sep=" "))
                )

    conn.executemany(
        """
        INSERT INTO events (user_id, event_type, query_text, parent_asin, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()

    n_suggest = sum(1 for row in rows if row[1] == "suggest")
    n_select = sum(1 for row in rows if row[1] == "select")
    return n_suggest, n_select
