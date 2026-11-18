"""Issue persistent identifiers to library records that do not have one yet.

    python scripts/assign_identifiers.py

Adds a ``pid`` to each new instrument, instrument version, construct and theory or framework,
records it in identifiers.csv, and marks retired records as retired there. Existing identifiers
are never changed. See IDENTIFIERS.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import identifiers as ids  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def with_pid_after(rec: dict, after: str) -> dict:
    """The record with "pid" placed right after ``after``, so it reads next to the record's id."""
    if "pid" not in rec:
        return rec
    out = {}
    for k, v in rec.items():
        if k == "pid":
            continue
        out[k] = v
        if k == after:
            out["pid"] = rec["pid"]
    return out


def dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sync_statuses(library: Path, instruments: dict, constructs: list, frameworks: list,
                  ledger: list[dict]) -> list[str]:
    """Mark retired records as retired in the ledger. Returns the identifiers changed."""
    by_pid = {rec.get("pid"): rec for _, _, rec in ids.records(instruments, constructs, frameworks)}
    changed = []
    for row in ledger:
        rec = by_pid.get(row["pid"])
        if rec is not None and ids.is_retired(rec) and row["status"] != "retired":
            row["status"] = "retired"
            changed.append(row["pid"])
    return changed


def main(library: Path = REPO, today: str | None = None) -> list[dict]:
    inst_paths = sorted((library / "instruments").glob("*.json"))
    instruments = {}
    for p in inst_paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        instruments[data["id"]] = data
    cons_doc = json.loads((library / "constructs.json").read_text(encoding="utf-8"))
    fw_doc = json.loads((library / "frameworks.json").read_text(encoding="utf-8"))
    constructs, frameworks = cons_doc["constructs"], fw_doc["frameworks"]

    ledger = ids.read_ledger(library)
    added = ids.assign(instruments, constructs, frameworks, ledger, today)
    retired = sync_statuses(library, instruments, constructs, frameworks, ledger)
    if not added and not retired:
        return []

    for p in inst_paths:
        data = json.loads(p.read_text(encoding="utf-8"))
        new = instruments[data["id"]]
        new["versions"] = [with_pid_after(v, "version_id") for v in new.get("versions", [])]
        if new != data or list(new) != list(data):
            dump(p, with_pid_after(new, "id"))
    cons_doc["constructs"] = [with_pid_after(c, "id") for c in constructs]
    dump(library / "constructs.json", cons_doc)
    fw_doc["frameworks"] = [with_pid_after(f, "id") for f in frameworks]
    dump(library / "frameworks.json", fw_doc)
    ids.write_ledger(library, ledger + added)
    return added


if __name__ == "__main__":
    added = main()
    for row in added:
        print(f"{row['pid']}  {row['type']:<10} {row['record']}")
    print(f"Issued {len(added)} identifier(s)." if added else "Every record already has an identifier.")
