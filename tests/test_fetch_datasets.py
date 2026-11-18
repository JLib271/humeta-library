# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dataset index is built from the STEMEd+ Commons Library's Data collection."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_datasets as F  # noqa: E402

API = F.K.API

HUMETA = {
    "profile": "humeta",
    "study": {
        "fields": ["education"], "discipline": ["anzsrc_3702"],
        "population": {"participant_roles": ["students"], "sample_size": 212},
        "evidence": {"study_designs": ["pre_post"]},
        "design": {"frameworks": ["expectancy_value"], "topic": "Climate understanding"},
        "constructs": [{"construct_id": "conceptual_understanding", "instrument_id": "gci", "version_id": "gci-v4-2014"}],
    },
    "education": {"education_levels": ["bachelors"]},
}


def record(rid, *, files=("data.csv", "humeta.json"), files_public=True, subjects=(), record_access="public"):
    return {
        "id": rid, "pids": {"doi": {"identifier": f"10.17613/{rid}"}},
        "links": {"self_html": f"https://works.hcommons.org/records/{rid}"},
        "metadata": {"title": f"Dataset {rid}", "publication_date": "2026-10-01",
                     "creators": [{"person_or_org": {"name": "Researcher, A."}}],
                     "description": "<p>Pre &amp; post <b>scores</b>.</p>",
                     "rights": [{"id": "cc-by-4.0", "title": {"en": "Creative Commons Attribution 4.0"}}],
                     "resource_type": {"id": "dataset", "title": {"en": "Dataset"}},
                     "subjects": [{"subject": s} for s in subjects],
                     "related_identifiers": [{"identifier": "10.1000/paper"}]},
        "access": {"record": record_access, "files": "public" if files_public else "restricted"},
        "files": {"entries": {f: {} for f in files}},
        "parent": {"communities": {"ids": [], "entries": [{"slug": "stemedplus-data"}]}},
    }


def fake(records, fail=False, published=None, slug="stemedplus-data"):
    calls = []

    def fetch(url):
        calls.append(url)
        if fail and f"/communities/{slug}/records" in url:
            raise OSError("offline")
        if url in (F.PUBLISHED_INDEX, F.PUBLISHED_STUDY_INDEX):
            if published is None:
                raise OSError("no site yet")
            return published
        if f"/communities/{slug}/records" in url:
            return {"hits": {"hits": records}}
        if url.endswith("/files/humeta.json/content"):
            return HUMETA
        if "/communities/" in url:
            raise OSError("not a STEMEd+ collection")
        raise AssertionError(url)

    fetch.calls = calls
    return fetch


def test_humeta_json_links_instruments_constructs_and_theories():
    index = F.build_index(fetch=fake([record("aaaaa-11111")]))
    d = index["datasets"][0]
    assert d["has_humeta"] and d["instruments"] == ["gci"] and d["versions"] == ["gci-v4-2014"]
    assert d["constructs"] == ["conceptual_understanding"] and d["frameworks"] == ["expectancy_value"]
    assert d["disciplines"] == ["anzsrc_3702"] and d["education_levels"] == ["bachelors"] and d["sample_size"] == 212
    assert d["url"] == "https://doi.org/10.17613/aaaaa-11111"
    assert d["description"] == "Pre & post scores."
    assert d["licenses"] == ["Creative Commons Attribution 4.0"] and d["related"] == ["10.1000/paper"]


def test_restricted_files_link_through_keywords_only():
    fetch = fake([record("bbbbb-22222", files_public=False,
                         subjects=["humeta:instrument:GCI", "humeta:construct:self_efficacy", "geoscience"])])
    d = F.build_index(fetch=fetch)["datasets"][0]
    assert not d["has_humeta"] and not any(u.endswith("/content") for u in fetch.calls)
    assert d["instruments"] == ["gci"] and d["constructs"] == ["self_efficacy"]
    assert d["keywords"] == ["geoscience"]


def test_keywords_add_to_humeta_json_without_duplicates():
    d = F.build_index(fetch=fake([record("ccccc-33333", subjects=["humeta:instrument:gci", "humeta:framework:sct"])]))["datasets"][0]
    assert d["instruments"] == ["gci"] and d["frameworks"] == ["expectancy_value", "sct"]


def test_no_humeta_file_means_no_links():
    d = F.build_index(fetch=fake([record("ddddd-44444", files=("data.csv",))]))["datasets"][0]
    assert not d["has_humeta"] and d["instruments"] == [] and d["constructs"] == []


def test_records_that_are_not_public_are_left_out():
    index = F.build_index(fetch=fake([record("eeeee-55555", record_access="restricted")]))
    assert index["datasets"] == []


def test_offline_reuses_the_published_index():
    published = {"format": "humeta-dataset-index", "datasets": [{"id": "old"}]}
    assert F.build_index(fetch=fake([], fail=True, published=published)) == published


def test_offline_without_a_published_index_is_empty():
    index = F.build_index(fetch=fake([], fail=True))
    assert index["datasets"] == [] and index["fetched"] is None


def test_deposit_and_collection_links():
    assert F.deposit_url() == "https://works.hcommons.org/uploads/new?community=stemedplus-data"
    assert F.collection_url() == "https://works.hcommons.org/collections/stemedplus-data"


def test_studies_collection_is_indexed_under_studies():
    index = F.build_index(fetch=fake([record("sssss-00001")], slug="stemedplus-studies"), kind="studies")
    assert index["format"] == "humeta-study-index" and index["collection"] == "stemedplus-studies"
    s = index["studies"][0]
    assert s["doi"] == "10.17613/sssss-00001" and s["instruments"] == ["gci"] and s["profile_doi"] == ""


def test_dataset_carries_the_study_doi_from_its_profile(monkeypatch):
    monkeypatch.setitem(HUMETA, "resource", {"identifier": {"value": "https://doi.org/10.17613/SSSSS-00001", "type": "DOI"}})
    d = F.build_index(fetch=fake([record("aaaaa-11111")]))["datasets"][0]
    assert d["profile_doi"] == "10.17613/sssss-00001"


def test_offline_studies_reuse_the_published_study_index():
    published = {"format": "humeta-study-index", "studies": [{"id": "old"}]}
    assert F.build_index(fetch=fake([], fail=True, published=published, slug="stemedplus-studies"), kind="studies") == published
