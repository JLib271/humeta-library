#!/usr/bin/env python3
# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the STEMEd+ Library's Data or Studies collection into an index the HuMeta Library links.

Datasets live in the STEMEd+ Commons Library, in the Data
subcollection; registered studies (a study's design, deposited from the HuMeta Portal's
Module 3 to give the study its own DOI) live in the Studies subcollection. This reads a
collection's public records and, for each, works out what it connects to in the HuMeta
Library:

* **humeta.json**: the HuMeta study profile attached to the deposit (downloaded from
  the HuMeta Portal). It gives the instruments and versions used, constructs measured,
  theories, disciplines, education levels, participants, designs, and sample size.
* **HuMeta keywords**: keywords such as ``humeta:instrument:gci``,
  ``humeta:construct:self_efficacy``, or ``humeta:framework:expectancy_value``, which
  the portal also gives depositors. They link deposits whose files are restricted
  (so humeta.json can't be read) and add to humeta.json when both are present.

Only public record metadata is read; restricted files are never downloaded. If
the STEMEd+ Commons Library can't be reached, the index published with the current website
is reused, so a failed fetch never empties the site's dataset pages.

    python scripts/fetch_datasets.py                    # writes _datasets.json
    python scripts/fetch_datasets.py --kind studies     # writes _studies.json
    python scripts/fetch_datasets.py --out PATH --collection stemedplus-data
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kcworks_lookup as K  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
#: The STEMEd+ Library's Data subcollection (collection slug)
DATA_COLLECTION = "stemedplus-data"
#: The STEMEd+ Library's Studies subcollection: registered studies, each with its own DOI
STUDIES_COLLECTION = "stemedplus-studies"
#: The indexes the current website publishes, reused when the STEMEd+ Commons Library can't be reached
PUBLISHED_INDEX = "https://jlib271.github.io/humeta-library/data/datasets.json"
PUBLISHED_STUDY_INDEX = "https://jlib271.github.io/humeta-library/data/studies.json"
#: kind -> (default collection, index format, published index)
KINDS = {
    "datasets": (DATA_COLLECTION, "humeta-dataset-index", PUBLISHED_INDEX),
    "studies": (STUDIES_COLLECTION, "humeta-study-index", PUBLISHED_STUDY_INDEX),
}
DOI = re.compile(r"10\.\d{4,9}/\S+")
HUMETA_FILE = re.compile(r"(^|[._-])humeta\.json$", re.I)
KEYWORD = re.compile(r"^\s*humeta:(instrument|version|construct|framework)\s*:\s*([A-Za-z0-9_.-]+)\s*$", re.I)
PAGE_SIZE = 100
MAX_PAGES = 50


def collection_url(slug: str = DATA_COLLECTION) -> str:
    return f"{K.SITE}/collections/{slug}"


def deposit_url(slug: str = DATA_COLLECTION) -> str:
    return f"{K.SITE}/uploads/new?community={slug}"


def plain_text(value: str | None, limit: int = 600) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    text = re.sub(r"\s+([.,;:!?)])", r"\1", text)
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def keyword_links(subjects: list) -> dict[str, list[str]]:
    """{'instruments': [...], 'versions': [...], 'constructs': [...], 'frameworks': [...]} from humeta: keywords."""
    out: dict[str, list[str]] = {"instruments": [], "versions": [], "constructs": [], "frameworks": []}
    for s in subjects or []:
        text = s.get("subject") if isinstance(s, dict) else s
        m = KEYWORD.match(str(text or ""))
        if m:
            out[m.group(1).lower() + "s"].append(m.group(2).lower() if m.group(1).lower() != "version" else m.group(2))
    return out


def humeta_links(record: dict) -> dict:
    """The links and facets a HuMeta study profile gives."""
    study = record.get("study") or {}
    edu = record.get("education") or {}
    population = study.get("population") or {}
    evidence = study.get("evidence") or {}
    constructs = study.get("constructs") or []
    return {
        "instruments": [c["instrument_id"] for c in constructs if c.get("instrument_id")],
        "versions": [c["version_id"] for c in constructs if c.get("version_id")],
        "constructs": [c["construct_id"] for c in constructs if c.get("construct_id")],
        "frameworks": list((study.get("design") or {}).get("frameworks") or []),
        "disciplines": list(study.get("discipline") or []),
        "fields": list(study.get("fields") or []),
        "education_levels": list(edu.get("education_levels") or []),
        "participant_roles": list(population.get("participant_roles") or []),
        "study_designs": list(evidence.get("study_designs") or []),
        "sample_size": population.get("sample_size"),
        "topic": (study.get("design") or {}).get("topic"),
        "profile_doi": _profile_doi(record),
    }


def _profile_doi(record: dict) -> str | None:
    """The study DOI a HuMeta profile records (set when the study was registered), lower-cased."""
    ident = (record.get("resource") or {}).get("identifier") or {}
    m = DOI.search(str(ident.get("value") or "")) if ident.get("type") == "DOI" else None
    return m.group(0).rstrip(".").lower() if m else None


def _unique(values) -> list:
    seen, out = set(), []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def read_humeta_file(record_id: str, files: list[str], fetch) -> dict | None:
    name = next((f for f in files if HUMETA_FILE.search(f)), None)
    if not name:
        return None
    try:
        data = fetch(f"{K.API}/records/{record_id}/files/{urllib.parse.quote(name)}/content")
    except Exception:  # noqa: BLE001 - an unreadable file just means no humeta.json links
        return None
    return data if isinstance(data, dict) and data.get("profile") == "humeta" else None


def entry(record: dict, fetch) -> dict:
    """One dataset in the index."""
    s = K.summarize(record, fetch)
    md = record.get("metadata", {})
    subjects = md.get("subjects") or []
    humeta = read_humeta_file(s["id"], s["files"], fetch) if s["files_public"] else None
    links = humeta_links(humeta) if humeta else {}
    kw = keyword_links(subjects)
    keywords = [str(x.get("subject") if isinstance(x, dict) else x) for x in subjects]
    return {
        "id": s["id"],
        "doi": s["doi"],
        "url": f"https://doi.org/{s['doi']}" if s["doi"] else s["url"],
        "title": s["title"] or s["id"],
        "creators": s["creators"],
        "date": md.get("publication_date") or "",
        "resource_type": s["resource_type"] or "",
        "description": plain_text(md.get("description")),
        "licenses": [lic["title"] for lic in s["licenses"]],
        "files_public": s["files_public"],
        "has_humeta": humeta is not None,
        "instruments": _unique([*links.get("instruments", []), *kw["instruments"]]),
        "versions": _unique([*links.get("versions", []), *kw["versions"]]),
        "constructs": _unique([*links.get("constructs", []), *kw["constructs"]]),
        "frameworks": _unique([*links.get("frameworks", []), *kw["frameworks"]]),
        "disciplines": links.get("disciplines", []),
        "fields": links.get("fields", []),
        "education_levels": links.get("education_levels", []),
        "participant_roles": links.get("participant_roles", []),
        "study_designs": links.get("study_designs", []),
        "sample_size": links.get("sample_size"),
        "topic": links.get("topic") or "",
        "keywords": [k for k in keywords if not KEYWORD.match(k)],
        "related": _unique((r.get("identifier") or "") for r in md.get("related_identifiers") or []),
        # The study this deposit belongs to: the DOI in its humeta.json (a dataset deposited after the study was
        # registered). For a deposit in the Studies collection that is normally empty: its own DOI is the study's.
        "profile_doi": links.get("profile_doi") or "",
    }


def fetch_collection(slug: str = DATA_COLLECTION, fetch=K.get_json) -> list[dict]:
    records, page = [], 1
    while page <= MAX_PAGES:
        data = fetch(f"{K.API}/communities/{slug}/records?size={PAGE_SIZE}&page={page}&sort=newest")
        hits = (data.get("hits") or {}).get("hits") or []
        records += hits
        if len(hits) < PAGE_SIZE:
            break
        page += 1
    return [entry(r, fetch) for r in records if (r.get("access") or {}).get("record", "public") == "public"]


def build_index(slug: str | None = None, fetch=K.get_json, kind: str = "datasets") -> dict:
    """The index of a collection (``kind`` "datasets" or "studies"), from the STEMEd+ Commons Library or, failing that,
    from the current website. Entries are under the ``kind`` key."""
    default_slug, fmt, published = KINDS[kind]
    slug = slug or default_slug
    try:
        entries = fetch_collection(slug, fetch)
        return {"format": fmt, "collection": slug, "collection_url": collection_url(slug),
                "fetched": date.today().isoformat(), kind: entries}
    except Exception as exc:  # noqa: BLE001
        print(f"Could not read the {slug} collection: {exc}", file=sys.stderr)
    try:
        previous = fetch(published)
        if previous.get("format") == fmt:
            print(f"Reusing the {kind} index published with the current website.", file=sys.stderr)
            return previous
    except Exception as exc:  # noqa: BLE001
        print(f"Could not read the published {kind} index either: {exc}", file=sys.stderr)
    return {"format": fmt, "collection": slug, "collection_url": collection_url(slug), "fetched": None, kind: []}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kind", choices=list(KINDS), default="datasets",
                    help="datasets (the Data collection) or studies (the Studies collection)")
    ap.add_argument("--out", type=Path, help="default: _datasets.json or _studies.json")
    ap.add_argument("--collection", help="STEMEd+ Commons Library collection slug (default: the kind's collection)")
    args = ap.parse_args(argv)
    out = args.out or REPO / f"_{args.kind}.json"
    index = build_index(args.collection, kind=args.kind)
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    entries = index[args.kind]
    linked = sum(1 for d in entries if d["instruments"] or d["constructs"] or d["frameworks"])
    print(f"{len(entries)} {args.kind} ({linked} linked to the library) written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
