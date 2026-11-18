"""Persistent identifiers: opaque, patterned, versioned with a dot, never reassigned or deleted (IDENTIFIERS.md)."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import identifiers as ids  # noqa: E402


def load():
    instruments = {}
    for p in (ROOT / "instruments").glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        instruments[d["id"]] = d
    constructs = json.loads((ROOT / "constructs.json").read_text(encoding="utf-8"))["constructs"]
    frameworks = json.loads((ROOT / "frameworks.json").read_text(encoding="utf-8"))["frameworks"]
    return instruments, constructs, frameworks, ids.read_ledger(ROOT)


def test_library_identifiers_are_valid():
    assert ids.check(*load()) == []


def test_identifiers_are_opaque_and_patterned():
    instruments, constructs, frameworks, _ = load()
    for kind, key, rec in ids.records(instruments, constructs, frameworks):
        assert ids.PATTERNS[kind].match(rec["pid"]), (kind, key)
    gci = instruments["gci"]
    assert gci["pid"] == "hmi0004" and "gci" not in gci["pid"]
    assert gci["versions"][0]["pid"] == "hmi0004.1"


def test_uri_and_compact_forms():
    assert ids.uri("hmi0004") == "https://w3id.org/humeta/instrument/hmi0004"
    assert ids.uri("hmi0004.1") == "https://w3id.org/humeta/instrument/hmi0004.1"
    assert ids.uri("hmc0012") == "https://w3id.org/humeta/construct/hmc0012"
    assert ids.curie("hmf0003") == "humeta.framework:hmf0003"
    with pytest.raises(ValueError):
        ids.uri("gci")


def test_frameworks_that_are_portal_choices_get_no_identifier():
    _, _, frameworks, _ = load()
    for fw in frameworks:
        assert ("pid" in fw) == (fw.get("kind") not in ids.NO_IDENTIFIER_KINDS)


def test_new_records_get_the_next_numbers_and_numbers_are_not_reused():
    instruments, constructs, frameworks, ledger = load()
    constructs = copy.deepcopy(constructs) + [{"id": "zz_new", "label": "New"}]
    inst = copy.deepcopy(instruments["gci"])
    inst["versions"].append({"version_id": "gci-v5"})
    instruments = {**instruments, "gci": inst, "zz": {"id": "zz", "versions": [{"version_id": "zz-1"}]}}
    added = ids.assign(instruments, constructs, frameworks, ledger, today="2026-12-01")
    got = {r["record"]: r["pid"] for r in added}
    assert got["gci/gci-v5"] == "hmi0004.2"
    assert got["zz"] == "hmi0007" and got["zz/zz-1"] == "hmi0007.1"
    assert got["zz_new"] == "hmc0033"
    assert ids.check(instruments, constructs, frameworks, ledger + added) == []


def test_deleted_or_reassigned_identifiers_fail():
    instruments, constructs, frameworks, ledger = load()
    gone = [c for c in constructs if c["id"] != "self_efficacy"]
    assert any("never deleted" in p for p in ids.check(instruments, gone, frameworks, ledger))
    swapped = copy.deepcopy(constructs)
    swapped[0]["pid"], swapped[1]["pid"] = swapped[1]["pid"], swapped[0]["pid"]
    assert any("never reassigned" in p for p in ids.check(instruments, swapped, frameworks, ledger))
    missing = copy.deepcopy(constructs)
    del missing[0]["pid"]
    assert any("assign_identifiers.py" in p for p in ids.check(instruments, missing, frameworks, ledger))


def test_retired_records_keep_their_identifier(tmp_path):
    import shutil
    import assign_identifiers
    for name in ("constructs.json", "frameworks.json", "identifiers.csv"):
        shutil.copy(ROOT / name, tmp_path / name)
    shutil.copytree(ROOT / "instruments", tmp_path / "instruments")
    doc = json.loads((tmp_path / "constructs.json").read_text(encoding="utf-8"))
    c = doc["constructs"][0]
    c["retired"] = {"on": "2026-12-01", "by": "committee", "replaced_by": doc["constructs"][1]["id"]}
    (tmp_path / "constructs.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    instruments, constructs, frameworks, ledger = (
        {d["id"]: d for d in (json.loads(p.read_text()) for p in (tmp_path / "instruments").glob("*.json"))},
        doc["constructs"], json.loads((tmp_path / "frameworks.json").read_text())["frameworks"], ids.read_ledger(tmp_path))
    assert any("marked 'active'" in p for p in ids.check(instruments, constructs, frameworks, ledger))
    assert assign_identifiers.main(tmp_path) == []
    row = next(r for r in ids.read_ledger(tmp_path) if r["pid"] == c["pid"])
    assert row["status"] == "retired"


def test_link_check_collects_outbound_links_only():
    import check_links
    found = check_links.links(ROOT)
    assert any(u.startswith("https://doi.org/10.") for u in found)
    assert not any(u.startswith("https://w3id.org/humeta") for u in found)
