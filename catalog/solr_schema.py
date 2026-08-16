from __future__ import annotations

import requests

from config import SOLR_CORE, SOLR_URL

FIELD_TYPES = [
    {
        # Edge n-grams at index time so a query token can match any prefix of
        # a title token (e.g. "hamm" matches "Hammock"); query analysis stays
        # plain so the query token itself isn't further split.
        "name": "text_prefix",
        "class": "solr.TextField",
        "indexAnalyzer": {
            "tokenizer": {"class": "solr.StandardTokenizerFactory"},
            "filters": [
                {"class": "solr.LowerCaseFilterFactory"},
                {"class": "solr.EdgeNGramFilterFactory", "minGramSize": "2", "maxGramSize": "20"},
            ],
        },
        "queryAnalyzer": {
            "tokenizer": {"class": "solr.StandardTokenizerFactory"},
            "filters": [{"class": "solr.LowerCaseFilterFactory"}],
        },
    }
]

FIELDS = [
    {"name": "title", "type": "text_prefix", "stored": True, "indexed": True},
    {"name": "taxonomy_path", "type": "text_general", "stored": True, "indexed": True},
    {"name": "store", "type": "string", "stored": True, "indexed": True},
    {"name": "main_category", "type": "string", "stored": True, "indexed": True},
    {"name": "price", "type": "pfloat", "stored": True, "indexed": True},
    {"name": "average_rating", "type": "pfloat", "stored": True, "indexed": True},
    {"name": "rating_number", "type": "pint", "stored": True, "indexed": True},
]


def _existing_names(kind: str, response_key: str) -> set[str]:
    resp = requests.get(f"{SOLR_URL}/{SOLR_CORE}/schema/{kind}")
    resp.raise_for_status()
    return {item["name"] for item in resp.json()[response_key]}


def ensure_schema() -> None:
    existing_types = _existing_names("fieldtypes", "fieldTypes")
    add_types = [ft for ft in FIELD_TYPES if ft["name"] not in existing_types]
    if add_types:
        resp = requests.post(
            f"{SOLR_URL}/{SOLR_CORE}/schema",
            json={"add-field-type": add_types},
        )
        resp.raise_for_status()

    existing_fields = _existing_names("fields", "fields")
    add_fields = [f for f in FIELDS if f["name"] not in existing_fields]
    if add_fields:
        resp = requests.post(
            f"{SOLR_URL}/{SOLR_CORE}/schema",
            json={"add-field": add_fields},
        )
        resp.raise_for_status()


if __name__ == "__main__":
    ensure_schema()
    print("Schema ensured.")
