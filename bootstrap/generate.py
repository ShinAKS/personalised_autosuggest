from __future__ import annotations

import random

from bootstrap.affinity import write_affinity_table
from bootstrap.events import simulate_events
from bootstrap.users import generate_users
from catalog.db import get_connection, init_schema
from config import NUM_SYNTHETIC_USERS, SYNTHETIC_RANDOM_SEED


def main():
    rng = random.Random(SYNTHETIC_RANDOM_SEED)
    conn = get_connection()
    init_schema(conn)

    affinity_rows = write_affinity_table(conn, rng)
    print(f"Demographic affinity rows: {affinity_rows}")

    users = generate_users(conn, NUM_SYNTHETIC_USERS, rng)
    print(f"Synthetic users: {len(users)}")

    n_suggest, n_select = simulate_events(conn, users, rng)
    print(f"Synthetic events — suggest: {n_suggest}, select: {n_select}")

    print("\nSample segment affinities (top 3 taxonomy roots):")
    for age, gender, region in [("13-17", "male", "US-West"), ("55-64", "female", "US-Midwest")]:
        top = conn.execute(
            """
            SELECT t.name, a.weight FROM demographic_affinity a
            JOIN taxonomy t ON t.id = a.taxonomy_root_id
            WHERE a.age_bracket = ? AND a.gender = ? AND a.region = ?
            ORDER BY a.weight DESC LIMIT 3
            """,
            (age, gender, region),
        ).fetchall()
        print(f"  {age} / {gender} / {region}: {[(name, round(w, 4)) for name, w in top]}")

    print("\nSample synthetic events:")
    samples = conn.execute(
        """
        SELECT e.user_id, e.event_type, e.query_text, i.title
        FROM events e LEFT JOIN items i ON i.parent_asin = e.parent_asin
        WHERE e.source = 'synthetic'
        ORDER BY RANDOM() LIMIT 8
        """
    ).fetchall()
    for user_id, event_type, query_text, title in samples:
        target = f" -> {title[:50]}" if title else ""
        print(f"  [{event_type:>7}] {user_id}  '{query_text}'{target}")

    conn.close()


if __name__ == "__main__":
    main()
