from __future__ import annotations

import sqlite3

from config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS taxonomy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES taxonomy(id),
    depth INTEGER NOT NULL,
    UNIQUE(name, parent_id)
);

CREATE TABLE IF NOT EXISTS items (
    parent_asin TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    features TEXT,
    price REAL,
    store TEXT,
    main_category TEXT,
    average_rating REAL,
    rating_number INTEGER,
    taxonomy_id INTEGER REFERENCES taxonomy(id)
);

CREATE INDEX IF NOT EXISTS idx_items_taxonomy ON items(taxonomy_id);
CREATE INDEX IF NOT EXISTS idx_taxonomy_parent ON taxonomy(parent_id);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    age_bracket TEXT NOT NULL,
    gender TEXT NOT NULL,
    region TEXT NOT NULL,
    is_synthetic INTEGER NOT NULL DEFAULT 0
);

-- Bootstrap prior: how strongly a demographic segment leans toward a top-level
-- taxonomy category. Synthetic (Phase 3) until real events (Phase 6) take over.
CREATE TABLE IF NOT EXISTS demographic_affinity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    age_bracket TEXT NOT NULL,
    gender TEXT NOT NULL,
    region TEXT NOT NULL,
    taxonomy_root_id INTEGER NOT NULL REFERENCES taxonomy(id),
    weight REAL NOT NULL,
    UNIQUE(age_bracket, gender, region, taxonomy_root_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    event_type TEXT NOT NULL CHECK(event_type IN ('suggest', 'select')),
    query_text TEXT NOT NULL,
    parent_asin TEXT REFERENCES items(parent_asin),
    source TEXT NOT NULL DEFAULT 'real' CHECK(source IN ('real', 'synthetic')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_demographic_affinity_segment
    ON demographic_affinity(age_bracket, gender, region);
"""


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_or_create_taxonomy_path(conn: sqlite3.Connection, breadcrumb: list[str]) -> int | None:
    """Walk/create a chain of taxonomy nodes for a breadcrumb list, returning the leaf node id."""
    parent_id = None
    node_id = None
    for depth, name in enumerate(breadcrumb):
        name = name.strip()
        if not name:
            continue
        row = conn.execute(
            "SELECT id FROM taxonomy WHERE name = ? AND parent_id IS ?",
            (name, parent_id),
        ).fetchone()
        if row:
            node_id = row[0]
        else:
            cur = conn.execute(
                "INSERT INTO taxonomy (name, parent_id, depth) VALUES (?, ?, ?)",
                (name, parent_id, depth),
            )
            node_id = cur.lastrowid
        parent_id = node_id
    return node_id


def taxonomy_roots(conn: sqlite3.Connection) -> dict[int, int]:
    """Map every taxonomy node id to its root ancestor id, via one full-table scan."""
    parent_of = dict(conn.execute("SELECT id, parent_id FROM taxonomy").fetchall())
    root_cache: dict[int, int] = {}

    def resolve(node_id: int) -> int:
        if node_id not in root_cache:
            parent_id = parent_of.get(node_id)
            root_cache[node_id] = node_id if parent_id is None else resolve(parent_id)
        return root_cache[node_id]

    return {node_id: resolve(node_id) for node_id in parent_of}


def taxonomy_path(conn: sqlite3.Connection, taxonomy_id: int | None) -> list[str]:
    """Walk from a leaf taxonomy node up to the root, returning the breadcrumb (root-first)."""
    path = []
    node_id = taxonomy_id
    while node_id is not None:
        row = conn.execute(
            "SELECT name, parent_id FROM taxonomy WHERE id = ?", (node_id,)
        ).fetchone()
        if row is None:
            break
        name, parent_id = row
        path.append(name)
        node_id = parent_id
    return list(reversed(path))
