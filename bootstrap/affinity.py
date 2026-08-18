from __future__ import annotations

import math
import random
import sqlite3
from collections import defaultdict

from config import AGE_BRACKETS, GENDERS, REGIONS

# Interest clusters used to give each demographic segment a non-trivial, interpretable
# prior over the catalog's (messy, ~90-node) real taxonomy roots, without hand-tuning a
# weight per (segment, root) pair. A root is assigned to the first cluster whose keyword
# appears in its name; unmatched roots fall into "general".
#
# The bias vectors below are illustrative placeholders for bootstrapping a cold-start
# ranker, not claims about real demographic behavior — they're fully superseded by real
# usage once Phase 6's feedback loop has enough events.
CLUSTER_KEYWORDS: dict[str, list[str]] = {
    "tech_electronics": [
        "electronic", "computer", "cell phone", "camera", "gps", "software",
        "video game", "amazon device", "apple product", "appstore", "fire phone",
        "office electronics", "portable audio", "home audio",
    ],
    "fashion_beauty": ["fashion", "beauty", "personal care", "jewelry", "clothing"],
    "home_living": [
        "home", "kitchen", "appliance", "tool", "patio", "lawn", "garden", "grill",
        "lighting", "janitorial",
    ],
    "family_kids": ["baby", "toys", "kids"],
    "media_entertainment": [
        "book", "movie", "cd", "vinyl", "digital music", "prime video", "audible",
        "kindle", "magazine", "action", "adventure", "animation", "comedy",
        "documentary", "drama", "fantasy", "historical", "horror", "international",
        "faith", "romance", "science fiction", "suspense", "western", "unscripted",
        "special interest", "music videos",
    ],
    "health_grocery": ["health", "household", "grocery", "medical", "mobility"],
    "sports_outdoors_auto": [
        "sport", "outdoor", "hunting", "fishing", "automotive", "industrial",
        "scientific", "remote & app controlled",
    ],
    "hobbies_crafts": [
        "art", "craft", "sewing", "handmade", "collectible", "musical instrument",
        "office product",
    ],
    "gifts_misc": ["gift card", "subscription box"],
}

# Additive bonuses on top of a flat baseline score of 1.0 per cluster; summed across
# age/gender/region then passed through softmax to get per-segment cluster weights.
AGE_BIAS: dict[str, dict[str, float]] = {
    "13-17": {"media_entertainment": 1.5, "tech_electronics": 1.2, "family_kids": 0.3},
    "18-24": {"tech_electronics": 1.3, "fashion_beauty": 1.0, "media_entertainment": 1.0},
    "25-34": {"tech_electronics": 1.0, "home_living": 0.8, "family_kids": 0.6, "fashion_beauty": 0.6},
    "35-44": {"family_kids": 1.3, "home_living": 1.0, "health_grocery": 0.6},
    "45-54": {"home_living": 1.2, "health_grocery": 0.9, "hobbies_crafts": 0.6},
    "55-64": {"health_grocery": 1.3, "home_living": 1.1, "hobbies_crafts": 0.7, "gifts_misc": 0.4},
    "65+": {"health_grocery": 1.5, "home_living": 1.0, "gifts_misc": 0.6, "media_entertainment": 0.4},
}
GENDER_BIAS: dict[str, dict[str, float]] = {
    "female": {"fashion_beauty": 1.1, "family_kids": 0.5, "home_living": 0.4},
    "male": {"tech_electronics": 0.6, "sports_outdoors_auto": 0.8, "hobbies_crafts": 0.3},
    "nonbinary": {},
}
REGION_BIAS: dict[str, dict[str, float]] = {
    "US-Northeast": {"media_entertainment": 0.3, "fashion_beauty": 0.2},
    "US-South": {"sports_outdoors_auto": 0.3, "gifts_misc": 0.2},
    "US-Midwest": {"home_living": 0.3, "family_kids": 0.2},
    "US-West": {"tech_electronics": 0.3, "health_grocery": 0.2},
}

AFFINITY_JITTER_SIGMA = 0.15  # log-normal spread applied per root so weights within a
# cluster aren't perfectly uniform


def _cluster_for(root_name: str) -> str:
    lowered = root_name.lower()
    for cluster, keywords in CLUSTER_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return cluster
    return "general"


def _segment_cluster_scores(age: str, gender: str, region: str) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(lambda: 1.0)
    for bias in (AGE_BIAS.get(age, {}), GENDER_BIAS.get(gender, {}), REGION_BIAS.get(region, {})):
        for cluster, bonus in bias.items():
            scores[cluster] += bonus
    return scores


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    peak = max(scores.values())
    exps = {cluster: math.exp(score - peak) for cluster, score in scores.items()}
    total = sum(exps.values())
    return {cluster: value / total for cluster, value in exps.items()}


def generate_affinity_weights(conn: sqlite3.Connection, rng: random.Random) -> list[tuple]:
    """Returns (age_bracket, gender, region, taxonomy_root_id, weight) rows, weights
    summing to 1 within each demographic segment."""
    root_names = dict(conn.execute("SELECT id, name FROM taxonomy WHERE parent_id IS NULL").fetchall())
    roots_by_cluster: dict[str, list[int]] = defaultdict(list)
    for root_id, name in root_names.items():
        roots_by_cluster[_cluster_for(name)].append(root_id)

    all_clusters = set(CLUSTER_KEYWORDS) | set(roots_by_cluster) | {"general"}

    rows = []
    for age in AGE_BRACKETS:
        for gender in GENDERS:
            for region in REGIONS:
                scores = _segment_cluster_scores(age, gender, region)
                for cluster in all_clusters:
                    scores.setdefault(cluster, 1.0)
                cluster_probs = _softmax(scores)

                segment_weights: dict[int, float] = {}
                for cluster, prob in cluster_probs.items():
                    root_ids = roots_by_cluster.get(cluster, [])
                    if not root_ids:
                        continue
                    share = prob / len(root_ids)
                    for root_id in root_ids:
                        segment_weights[root_id] = share * rng.lognormvariate(0, AFFINITY_JITTER_SIGMA)

                total = sum(segment_weights.values())
                rows.extend(
                    (age, gender, region, root_id, weight / total)
                    for root_id, weight in segment_weights.items()
                )
    return rows


def write_affinity_table(conn: sqlite3.Connection, rng: random.Random) -> int:
    conn.execute("DELETE FROM demographic_affinity")
    rows = generate_affinity_weights(conn, rng)
    conn.executemany(
        """
        INSERT INTO demographic_affinity (age_bracket, gender, region, taxonomy_root_id, weight)
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    return len(rows)
