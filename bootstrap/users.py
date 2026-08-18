from __future__ import annotations

import random
import sqlite3

from config import AGE_BRACKETS, GENDERS, REGIONS


def generate_users(conn: sqlite3.Connection, n: int, rng: random.Random) -> list[tuple[str, str, str, str]]:
    """Creates n synthetic users with random demographics. Returns
    (user_id, age_bracket, gender, region) for each, replacing any prior synthetic users."""
    # Events reference users via a foreign key, so synthetic events must go first.
    conn.execute("DELETE FROM events WHERE source = 'synthetic'")
    conn.execute("DELETE FROM users WHERE is_synthetic = 1")

    users = [
        (f"synth-{i:06d}", rng.choice(AGE_BRACKETS), rng.choice(GENDERS), rng.choice(REGIONS))
        for i in range(n)
    ]
    conn.executemany(
        "INSERT INTO users (user_id, age_bracket, gender, region, is_synthetic) VALUES (?, ?, ?, ?, 1)",
        users,
    )
    conn.commit()
    return users
