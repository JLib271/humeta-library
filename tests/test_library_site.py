# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Library website builds, links work, and item text follows the access rules."""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_site as B  # noqa: E402  (also puts the HuMeta Portal's code on the path)
from oem.library import Library  # noqa: E402


def load() -> Library:
    return Library.load(ROOT)


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "_site"
    B.main(["--out", str(out)])
    return out


def test_every_record_has_a_page(site):
    lib = load()
    for iid in lib.instruments:
        assert (site / "instruments" / lib.instruments[iid]["pid"] / "index.html").is_file()
    for fid, fw in lib.frameworks.items():
        if fw.get("kind") in ("theory", "lens"):
            assert (site / "frameworks" / fw["pid"] / "index.html").is_file()
    for cid in lib.constructs:
        assert (site / "constructs" / lib.constructs[cid]["pid"] / "index.html").is_file()
    for page in ("index.html", "reference/index.html", "about/index.html", "404.html", "sitemap.xml"):
        assert (site / page).is_file()


def test_page_urls_match_the_app(site):
    """The portal links to record pages by the same address scheme the site uses."""
    from oem import vocab
    lib = load()
    iid = next(iter(lib.instruments))
    url = vocab.library_page_url(lib, "instruments", iid)
    assert url.endswith(f"/instruments/{lib.instruments[iid]['pid']}/")
    assert (site / url.removeprefix(vocab.LIBRARY_SITE_URL) / "index.html").is_file()


def test_published_archive_is_the_library(site, tmp_path):
    import hashlib
    import tarfile
    manifest = json.loads((site / "data" / "library.json").read_text(encoding="utf-8"))
    archive = site / "data" / manifest["archive"]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["sha256"]
    with tarfile.open(archive) as tar:
        names = tar.getnames()
        tar.extractall(tmp_path, filter="data")
    assert len(names) == manifest["files"] and all(n.startswith("library/") for n in names)
    assert not any(n.startswith(("library/scripts", "library/site", "library/tests", "library/suggestions")) for n in names)
    published = Library.load(tmp_path / "library")
    assert set(published.instruments) == set(load().instruments)
    assert published.item_files.keys() == load().item_files.keys()


def test_archive_is_reproducible(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    B.main(["--out", str(a)])
    B.main(["--out", str(b)])
    assert (a / "data" / "library.tar.gz").read_bytes() == (b / "data" / "library.tar.gz").read_bytes()


def test_internal_links_resolve(site):
    bad = []
    for page in site.rglob("*.html"):
        if page.name == "404.html":
            continue
        for url in re.findall(r'(?:href|src)="([^"]+)"', page.read_text(encoding="utf-8")):
            if url.startswith(("http", "mailto:", "#")):
                continue
            target = (page.parent / unquote(url.split("#")[0].split("?")[0])).resolve()
            if target.is_dir():
                target = target / "index.html"
            if not target.exists():
                bad.append((str(page.relative_to(site)), url))
    assert not bad, bad[:5]


def test_downloads(site):
    lib = load()
    with (site / "data" / "instruments.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == len(lib.instruments)
    with (site / "data" / "evidence.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == len(lib.evidence)
    for iid in lib.instruments:
        assert json.loads((site / "data" / "instruments" / f"{lib.instruments[iid]['pid']}.json").read_text(encoding="utf-8"))["id"] == iid
    index = json.loads(re.search(r'<script type="application/json" id="index">(.*?)</script>',
                                 (site / "index.html").read_text(encoding="utf-8"), re.S).group(1))
    assert {r["type"] for r in index} == {"instrument", "theory", "construct"}


def _fake_library(tmp_path, shareable: bool) -> Path:
    """A copy of the library with one instrument whose item text sharing is switched on or off."""
    root = tmp_path / "library"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", "_site", "__pycache__"))
    path = root / "instruments" / "gci.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["access"]["item_text_shareable"] = shareable
    path.write_text(json.dumps(rec), encoding="utf-8")
    return root


@pytest.mark.parametrize("shareable", [True, False])
def test_item_text_and_images_follow_access(tmp_path, shareable):
    out = tmp_path / "_site"
    B.main(["--out", str(out), "--library", str(_fake_library(tmp_path, shareable))])
    html = (out / "instruments" / "hmi0004" / "index.html").read_text(encoding="utf-8")
    stem = json.loads((ROOT / "items" / "gci" / "gci-v4-2014.json").read_text(encoding="utf-8"))["items"][0]["stem"]
    figures = list((out / "instruments" / "hmi0004" / "figures").glob("*.png")) if (out / "instruments" / "hmi0004" / "figures").exists() else []
    if shareable:
        assert B.h(stem) in html and figures
    else:
        assert B.h(stem) not in html and not figures
        assert "Item text is not republished here" in html


def test_answer_keys_never_shown_without_permission(site):
    lib = load()
    for iid, inst in lib.instruments.items():
        if not inst.get("access", {}).get("answer_key_shareable"):
            html = (site / "instruments" / lib.instruments[iid]["pid"] / "index.html").read_text(encoding="utf-8")
            assert ">correct</span>" not in html


def test_instrument_filters(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    for facet in ("itype", "part", "level", "disc"):
        assert f'data-facet="{facet}"' in html
    index = json.loads(re.search(r'id="index">(.*?)</script>', html, re.S).group(1))
    assert all("facets" in r for r in index if r["type"] == "instrument")


def test_compare_page_and_profiles(site):
    html = (site / "compare" / "index.html").read_text(encoding="utf-8")
    lib = load()
    assert html.count("<tr data-") == len(lib.instruments)
    page = (site / "instruments" / "hmi0006" / "index.html").read_text(encoding="utf-8")
    assert 'id="profile"' in page and "15 values, 0.52 to 0.93; guide &gt; 0.7" in page
    assert (site / "data" / "evidence_profiles.csv").is_file()
    assert 'id="rubric"' in (site / "about" / "index.html").read_text(encoding="utf-8")


def test_recommend_page_and_issue_forms(site):
    import yaml
    page = (site / "recommend" / "index.html").read_text(encoding="utf-8")
    assert "issues/new?template=instrument_submission.yml" in page
    assert "library_correction.yml" in (site / "instruments" / "hmi0004" / "index.html").read_text(encoding="utf-8")
    form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "instrument_submission.yml").read_text(encoding="utf-8"))
    ids = {b.get("id") for b in form["body"]}
    required = {b["id"] for b in form["body"] if b.get("validations", {}).get("required")}
    assert required == {"name", "citation", "measures"}
    lib = load()
    for cat in lib.rubric:  # the form's evidence checklist follows the rubric
        block = next(b for b in form["body"] if b.get("id") == f"rubric_{cat['id']}")
        assert [o["label"][0] for o in block["attributes"]["options"]] == [c["id"] for c in cat["criteria"]]
    assert "confirm" in ids
    assert (ROOT / ".github" / "ISSUE_TEMPLATE" / "library_correction.yml").is_file()


def test_commons_deposits(site):
    page = (site / "instruments" / "hmi0004" / "index.html").read_text(encoding="utf-8")
    assert 'id="commons"' in page and "10.17613/wnm5z-00x75" in page
    assert "works.hcommons.org/collections/humetainstrumentlibrary" in (site / "recommend" / "index.html").read_text(encoding="utf-8")
    assert "Join free" in (site / "index.html").read_text(encoding="utf-8")
    import yaml
    form = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "instrument_submission.yml").read_text(encoding="utf-8"))
    ids = {b.get("id") for b in form["body"]}
    assert {"commons_link", "commons_contents", "rights_holder"} <= ids and "commons_license" not in ids


def test_dataset_pages_and_backlinks(tmp_path):
    out = tmp_path / "site"
    B.main(["--out", str(out), "--datasets", str(ROOT / "tests" / "sample_datasets.json")])
    listing = (out / "datasets" / "index.html").read_text(encoding="utf-8")
    assert "Deposits <span class=\"count\">(2)</span>" in listing and 'href="aaaaa-11111/"' in listing
    page = (out / "datasets" / "aaaaa-11111" / "index.html").read_text(encoding="utf-8")
    assert 'href="../../instruments/hmi0004/"' in page and "made_up_theory" in page and "not in the library yet" in page
    assert 'href="../bbbbb-22222/"' in page  # shares the GCI
    gci = (out / "instruments" / "hmi0004" / "index.html").read_text(encoding="utf-8")
    assert 'href="../../datasets/aaaaa-11111/"' in gci and 'href="../../datasets/bbbbb-22222/"' in gci
    assert json.loads((out / "data" / "datasets.json").read_text(encoding="utf-8"))["datasets"][0]["id"]


def test_no_datasets_still_builds_the_datasets_page(tmp_path):
    out = tmp_path / "site"
    B.main(["--out", str(out), "--datasets", str(tmp_path / "missing.json")])
    assert "No datasets have been deposited" in (out / "datasets" / "index.html").read_text(encoding="utf-8")
    assert json.loads((out / "data" / "datasets.json").read_text(encoding="utf-8"))["datasets"] == []


def test_study_pages_link_datasets_and_library_records(tmp_path):
    out = tmp_path / "site"
    B.main(["--out", str(out), "--datasets", str(ROOT / "tests" / "sample_datasets.json"),
            "--studies", str(ROOT / "tests" / "sample_studies.json")])
    listing = (out / "studies" / "index.html").read_text(encoding="utf-8")
    assert "Registered studies <span class=\"count\">(1)</span>" in listing and 'href="sssss-00001/"' in listing
    page = (out / "studies" / "sssss-00001" / "index.html").read_text(encoding="utf-8")
    assert 'href="../../instruments/hmi0004/"' in page
    assert 'href="../../datasets/aaaaa-11111/"' in page and 'href="../../datasets/bbbbb-22222/"' not in page
    dataset = (out / "datasets" / "aaaaa-11111" / "index.html").read_text(encoding="utf-8")
    assert 'href="../../studies/sssss-00001/"' in dataset
    gci = (out / "instruments" / "hmi0004" / "index.html").read_text(encoding="utf-8")
    assert 'href="../../studies/sssss-00001/"' in gci
    assert json.loads((out / "data" / "studies.json").read_text(encoding="utf-8"))["studies"][0]["id"] == "sssss-00001"


def test_no_studies_still_builds_the_studies_page(tmp_path):
    out = tmp_path / "site"
    B.main(["--out", str(out), "--datasets", str(tmp_path / "missing.json"), "--studies", str(tmp_path / "missing.json")])
    assert "No studies have been registered" in (out / "studies" / "index.html").read_text(encoding="utf-8")
    assert json.loads((out / "data" / "studies.json").read_text(encoding="utf-8"))["studies"] == []


def test_records_carry_persistent_identifiers(site):
    page = (site / "instruments" / "hmi0004" / "index.html").read_text(encoding="utf-8")
    assert "https://w3id.org/humeta/instrument/hmi0004" in page and "Libarkin2005V4" in page
    assert "https://w3id.org/humeta/instrument/hmi0004.1" in page and 'id="version-1"' in page
    assert "humeta.instrument:hmi0004" in page and "Cite this record" in page
    ld = json.loads(re.search(r'application/ld\+json">(.*?)</script>', page, re.S).group(1).replace("<\\/", "</"))
    assert ld["@id"] == "https://w3id.org/humeta/instrument/hmi0004"
    dc = json.loads((site / "data" / "datacite" / "hmi0004.json").read_text(encoding="utf-8"))
    assert dc["alternateIdentifiers"][0] == {"alternateIdentifier": "https://w3id.org/humeta/instrument/hmi0004",
                                             "alternateIdentifierType": "URL"}
    se = next(c for c in Library.load(ROOT).constructs.values() if c["id"] == "self_efficacy")
    assert f"https://w3id.org/humeta/construct/{se['pid']}" in (
        site / "constructs" / se["pid"] / "index.html").read_text(encoding="utf-8")
    rules = (ROOT / "w3id" / "ids" / "humeta" / ".htaccess").read_text(encoding="utf-8")
    for kind in ("instrument", "construct", "framework", "metadata-code"):
        assert f"^{kind}" in rules


def test_one_address_per_record(site):
    """Pages and data files live at the persistent identifier only: no name-based copies."""
    assert (site / "instruments" / "hmi0004" / "index.html").is_file()
    assert not (site / "instruments" / "gci").exists()
    assert (site / "data" / "instruments" / "hmi0004.json").is_file()
    assert not (site / "data" / "instruments" / "gci.json").exists()
    assert (site / "data" / "items" / "hmi0004" / "hmi0004.1.json").is_file()
    assert not (site / "constructs" / "self-efficacy").exists()


def test_item_crosswalk_shows_possible_and_confirmed_links():
    import types
    inst = {"id": "demo", "pid": "hmi0099"}
    versions = [{"version_id": "v1", "label": "First"}, {"version_id": "v2", "label": "Second"}]
    files = [("v1", {"items": [{"item_id": "q01", "number": "1"}, {"item_id": "q02", "number": "2"}]}),
             ("v2", {"items": [{"item_id": "q01", "number": "3"},
                               {"item_id": "q10", "number": "1", "derived_from": [
                                   {"item_id": "q02", "relation": "reworded", "status": "possible"}]},
                               {"item_id": "q11", "number": "2", "derived_from": {
                                   "item_id": "q02", "relation": "split", "status": "confirmed",
                                   "basis": "developer_documentation"}}]})]
    html = B.Site.crosswalk(types.SimpleNamespace(table=B.Site.table), inst, files, versions)
    assert "No. in First" in html and "No. in Second" in html and 'id="item-q10"' in html
    assert "Possible links" in html and "Confirmed links" in html and "1 possible link(s) await checking" in html
    assert "source of: split" in html  # q02 shows the confirmed link from q11
    assert "https://w3id.org/humeta/instrument/hmi0099/item/" in html



def test_search_index_has_identifiers_developers_and_codes(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    data = re.search(r'<script type="application/json" id="index">(.*?)</script>', html, re.S)
    records = json.loads(data.group(1).replace("<\\/", "</"))
    gci = next(r for r in records if r.get("pid") == "hmi0004")
    assert gci["url"] == "instruments/hmi0004/"
    assert "Libarkin" in gci["text"] and "Libarkin2005V4" in gci["text"]
    assert {r["pid"] for r in records if r["type"] == "construct"} >= {"hmc0024"}
