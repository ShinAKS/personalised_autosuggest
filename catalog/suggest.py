from __future__ import annotations

import requests

from config import SOLR_CORE, SOLR_URL


def suggest(text: str, limit: int = 10) -> list[dict]:
    """Non-personalized candidate generation: prefix/text match over Solr, ranked by
    Solr relevance with rating_number as a tiebreak for popularity."""
    text = text.strip()
    if not text:
        return []

    resp = requests.get(
        f"{SOLR_URL}/{SOLR_CORE}/select",
        params={
            "q": f"title:({text}) OR taxonomy_path:({text})",
            "defType": "edismax",
            "qf": "title^2 taxonomy_path",
            "sort": "score desc, rating_number desc",
            "rows": limit,
            "fl": "id,title,taxonomy_path,store,price,average_rating,rating_number,score",
        },
    )
    resp.raise_for_status()
    return resp.json()["response"]["docs"]


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "cat"
    for doc in suggest(query):
        print(f"{doc['score']:.2f}  {doc['title'][:70]}  [{doc.get('taxonomy_path', '')}]")
