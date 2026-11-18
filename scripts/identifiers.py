"""HuMeta persistent identifiers: patterns, the ledger of issued identifiers, and their checks.

The rules are set out in IDENTIFIERS.md, which follows McMurry et al. (2017), "Identifiers for the
21st century", PLOS Biology 15(6): e2001414, https://doi.org/10.1371/journal.pbio.2001414.

In short:

* Identifiers are opaque. ``hmi0004`` says it is an instrument (the type letter) and nothing else:
  not its name, acronym, authors or year. Names and metadata codes are labels, shown next to it.
* Each type has its own pattern and prefix (``humeta.instrument:hmi0004``) bound to one URI pattern
  (``https://w3id.org/humeta/instrument/hmi0004``).
* A version of an instrument is its identifier, a dot and a number, in the order HuMeta added the
  versions: ``hmi0004.1``. The number is HuMeta's, not the publisher's version name.
* An identifier, once issued, is never reassigned or deleted. identifiers.csv records every one;
  the validator fails if one disappears from the library or points at a different record.
"""
from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path

PERSISTENT_BASE = "https://w3id.org/humeta/"

#: type -> (letter in the local ID, path in the URI, CURIE prefix)
TYPES = {
    "instrument": ("i", "instrument", "humeta.instrument"),
    "version": ("i", "instrument", "humeta.instrument"),
    "construct": ("c", "construct", "humeta.construct"),
    "framework": ("f", "framework", "humeta.framework"),
}

PATTERNS = {
    "instrument": re.compile(r"^hmi[0-9]{4}$"),
    "version": re.compile(r"^hmi[0-9]{4}\.[1-9][0-9]*$"),
    "construct": re.compile(r"^hmc[0-9]{4}$"),
    "framework": re.compile(r"^hmf[0-9]{4}$"),
}

#: Framework kinds that are choices in the portal rather than records, and get no identifier
NO_IDENTIFIER_KINDS = ("own", "exploratory")

LEDGER = "identifiers.csv"
LEDGER_FIELDS = ["pid", "type", "record", "issued_on", "status"]


def uri(pid: str) -> str:
    """The persistent URI of an identifier: https://w3id.org/humeta/<type>/<pid>."""
    for kind, pattern in PATTERNS.items():
        if pattern.match(pid):
            return f"{PERSISTENT_BASE}{TYPES[kind][1]}/{pid}"
    raise ValueError(f"not a HuMeta identifier: {pid!r}")


def curie(pid: str) -> str:
    """The compact form, prefix:local ID, e.g. humeta.instrument:hmi0004."""
    for kind, pattern in PATTERNS.items():
        if pattern.match(pid):
            return f"{TYPES[kind][2]}:{pid}"
    raise ValueError(f"not a HuMeta identifier: {pid!r}")


def read_ledger(library: Path) -> list[dict]:
    path = library / LEDGER
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_ledger(library: Path, rows: list[dict]) -> None:
    with (library / LEDGER).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def records(instruments: dict, constructs: list, frameworks: list) -> list[tuple[str, str, dict]]:
    """Every record that carries an identifier, as (type, record key, record).

    The record key is the library's own id, and for a version ``<instrument id>/<version id>``.
    """
    out = []
    for iid in sorted(instruments):
        inst = instruments[iid]
        out.append(("instrument", iid, inst))
        for v in inst.get("versions", []):
            out.append(("version", f"{iid}/{v['version_id']}", v))
    for c in sorted(constructs, key=lambda c: c["id"]):
        out.append(("construct", c["id"], c))
    for fw in sorted(frameworks, key=lambda f: f["id"]):
        if fw.get("kind") not in NO_IDENTIFIER_KINDS:
            out.append(("framework", fw["id"], fw))
    return out


def is_retired(rec: dict) -> bool:
    return bool(rec.get("retired"))


def check(instruments: dict, constructs: list, frameworks: list, ledger: list[dict]) -> list[str]:
    """Problems with the identifiers: missing, malformed, duplicated, reassigned, or deleted."""
    problems = []
    fix = " Run python scripts/assign_identifiers.py to issue identifiers to new records."
    seen: dict[str, str] = {}
    current: dict[str, tuple[str, str, dict]] = {}
    for kind, key, rec in records(instruments, constructs, frameworks):
        pid = rec.get("pid")
        if not pid:
            problems.append(f"{kind} {key}: has no persistent identifier (pid).{fix}")
            continue
        if not PATTERNS[kind].match(pid):
            problems.append(f"{kind} {key}: pid {pid!r} does not match {PATTERNS[kind].pattern}")
            continue
        if kind == "version":
            parent = instruments[key.split("/")[0]].get("pid")
            if parent and not pid.startswith(parent + "."):
                problems.append(f"version {key}: pid {pid} must be its instrument's pid ({parent}), a dot and a number")
        if pid in seen:
            problems.append(f"{kind} {key}: pid {pid} is already used by {seen[pid]}")
            continue
        seen[pid] = f"{kind} {key}"
        current[pid] = (kind, key, rec)

    issued = {}
    for row in ledger:
        pid = row.get("pid", "")
        if pid in issued:
            problems.append(f"{LEDGER}: {pid} is listed twice")
        issued[pid] = row
    for pid, (kind, key, rec) in current.items():
        row = issued.get(pid)
        if row is None:
            problems.append(f"{kind} {key}: pid {pid} is not in {LEDGER}.{fix}")
            continue
        if row["type"] != kind or row["record"] != key:
            problems.append(f"{kind} {key}: pid {pid} was issued to {row['type']} {row['record']}. "
                            "Identifiers are never reassigned; give this record a new one.")
        status = "retired" if is_retired(rec) else "active"
        if row.get("status") != status:
            problems.append(f"{LEDGER}: {pid} is marked {row.get('status')!r}, but the record is {status}")
    for pid, row in issued.items():
        if pid not in current:
            problems.append(f"{LEDGER}: {pid} ({row['type']} {row['record']}) is no longer in the library. "
                            "Identifiers are never deleted: keep the record and mark it retired instead.")
    return problems


def assign(instruments: dict, constructs: list, frameworks: list, ledger: list[dict],
           today: str | None = None) -> list[dict]:
    """Give every record without a pid the next free one. Changes the records in place.

    Returns the ledger rows added. Numbers are never reused, including those of retired records.
    """
    today = today or date.today().isoformat()
    used = {row["pid"] for row in ledger} | {rec["pid"] for _, _, rec in records(instruments, constructs, frameworks)
                                             if rec.get("pid")}

    def next_number(prefix: str) -> int:
        nums = [int(p[len(prefix):]) for p in used if re.fullmatch(re.escape(prefix) + r"[0-9]{4}", p)]
        return max(nums, default=0) + 1

    added = []
    for kind, key, rec in records(instruments, constructs, frameworks):
        if rec.get("pid"):
            continue
        if kind == "version":
            parent = instruments[key.split("/")[0]]["pid"]
            n = max([int(p.split(".")[1]) for p in used if p.startswith(parent + ".")], default=0) + 1
            pid = f"{parent}.{n}"
        else:
            prefix = "hm" + TYPES[kind][0]
            pid = f"{prefix}{next_number(prefix):04d}"
        rec["pid"] = pid
        used.add(pid)
        added.append({"pid": pid, "type": kind, "record": key, "issued_on": today,
                      "status": "retired" if is_retired(rec) else "active"})
    return added
