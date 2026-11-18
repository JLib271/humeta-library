# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The validator accepts the library and rejects terms that aren't current HuMeta terms."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import validate_library  # noqa: E402


def _vocabularies() -> str:
    """The HuMeta profile vocabularies from the HuMeta checkout the site builder uses."""
    import build_site
    path = build_site.HUMETA / "standard" / "humeta" / "vocabularies.json"
    if not path.is_file():
        pytest.skip("no HuMeta checkout with the profile")
    return str(path)


def _copy(tmp_path) -> Path:
    root = tmp_path / "library"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".humeta", "_site", "__pycache__"))
    return root


def test_library_is_valid():
    assert validate_library.main(ROOT, _vocabularies()) == 0


def test_validator_rejects_library_only_and_deprecated_terms(tmp_path):
    root = _copy(tmp_path)
    path = root / "instruments" / "gci.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["disciplines"] = ["geoscience"]          # deprecated
    rec["education_levels"] = ["undergraduate"]  # the library's old term
    path.write_text(json.dumps(rec), encoding="utf-8")
    assert validate_library.main(root, _vocabularies()) == 1


def test_unreadable_vocabularies_fail_when_named(tmp_path):
    assert validate_library.main(ROOT, str(tmp_path / "missing.json")) == 1


def test_instrument_metadata_codes_are_unique(tmp_path, capsys):
    root = _copy(tmp_path)
    path = root / "instruments" / "gci.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["metadata_code"] = "Pintrich1991"  # already the MSLQ's code
    path.write_text(json.dumps(rec), encoding="utf-8")
    assert validate_library.main(root, _vocabularies()) == 1
    assert "metadata_code 'Pintrich1991'" in capsys.readouterr().out


def test_psyctests_ids_must_be_dois(tmp_path):
    root = _copy(tmp_path)
    path = root / "instruments" / "mslq.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["identifiers"]["records"].append({"registry": "psyctests", "id": "9999-22083-000",
                                          "url": "https://doi.org/10.1037/t22083-000"})
    path.write_text(json.dumps(rec), encoding="utf-8")
    assert validate_library.main(root, _vocabularies()) == 1


def _second_version(root, links) -> None:
    """A made-up second GCI version in a copy of the library: its first item links to v4 items."""
    path = root / "instruments" / "gci.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    new = {k: v for k, v in rec["versions"][0].items() if k != "pid"}
    rec["versions"].append({**new, "version_id": "gci-test-v5", "code": "V5", "label": "Test version"})
    path.write_text(json.dumps(rec), encoding="utf-8")
    import assign_identifiers
    assign_identifiers.main(root, today="2026-11-18")  # the new version gets hmi0004.2
    items = [{"item_id": "q90", "number": "1", "response_type": "single_response", "derived_from": links},
             {"item_id": "q01", "number": "2", "response_type": "multiple_response"}]
    (root / "items" / "gci" / "gci-test-v5.json").write_text(
        json.dumps({"instrument_id": "gci", "version_id": "gci-test-v5", "items": items}), encoding="utf-8")


def test_items_can_link_across_versions_as_possible_or_confirmed(tmp_path, capsys):
    root = _copy(tmp_path)
    _second_version(root, [{"item_id": "q05", "relation": "reworded", "status": "possible"},
                           {"item_id": "q06", "relation": "merged", "status": "confirmed",
                            "basis": "developer_documentation", "checked_by": "Test", "checked_on": "2026-11-18"}])
    assert validate_library.main(root, _vocabularies()) == 0


def test_confirmed_links_need_a_basis_and_a_real_item(tmp_path, capsys):
    root = _copy(tmp_path)
    _second_version(root, [{"item_id": "q05", "relation": "reworded", "status": "confirmed"},
                           {"item_id": "q999", "relation": "reworded", "status": "possible"}])
    assert validate_library.main(root, _vocabularies()) == 1
    out = capsys.readouterr().out
    assert "needs a basis" in out and "'q999' not found" in out
