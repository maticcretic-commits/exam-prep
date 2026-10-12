#!/usr/bin/env python3
"""Extract sarkari-vacancies banks from the legacy index.html.

Reads the FULL raw page (never gh-api file stdout), evals the LISTINGS /
PIPELINE / DIRECTORY arrays with node (JS escapes), and writes
data/sarkari-vacancies.json in the unified schema.

Legacy note: 7 rows share ids with earlier rows (tnpsc-group4-2026 x2,
sci-jca-2026 x3, opsc-aee-2026 x2) — refresh artifacts, not distinct jobs.
All 106 rows are kept (exact count fidelity); duplicate ids are
disambiguated with a -2/-3 suffix so HTML anchors stay valid.
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW_URL = "https://raw.githubusercontent.com/maticcretic-commits/sarkari-vacancies/main/index.html"

NODE_EVAL = """
var fs = require('fs');
var html = fs.readFileSync(%(path)s, 'utf8');
function grab(name) {
  var m = html.match(new RegExp('(?:var|const|let)\\\\s+' + name + '\\\\s*=\\\\s*(\\\\[[\\\\s\\\\S]*?\\\\]);'));
  if (!m) { console.error('NOT FOUND: ' + name); process.exit(1); }
  return eval(m[1]);
}
process.stdout.write(JSON.stringify({LISTINGS: grab('LISTINGS'), PIPELINE: grab('PIPELINE'), DIRECTORY: grab('DIRECTORY')}));
"""


def main() -> int:
    raw_path = ROOT / "tools" / "extract" / ".sarkari-raw.html"
    print("downloading full raw page...")
    subprocess.run(["curl", "-sL", RAW_URL, "-o", str(raw_path), "--max-time", "120"], check=True)
    size = raw_path.stat().st_size
    print(f"  raw size: {size} bytes")
    assert size > 100_000, f"suspiciously small download: {size}"

    node_src = NODE_EVAL % {"path": json.dumps(str(raw_path))}
    r = subprocess.run(["node", "-e", node_src], capture_output=True, text=True)
    if r.returncode != 0:
        print("node eval failed:", r.stderr[:500])
        return 1
    raw = json.loads(r.stdout)
    ls, pipe, direc = raw["LISTINGS"], raw["PIPELINE"], raw["DIRECTORY"]
    print(f"  legacy counts: listings={len(ls)} pipeline={len(pipe)} directory={len(direc)}")
    assert len(ls) == 106, f"LISTINGS {len(ls)} != legacy 106"
    assert len(pipe) == 23, f"PIPELINE {len(pipe)} != legacy 23"
    assert len(direc) == 14, f"DIRECTORY {len(direc)} != legacy 14"

    seen = Counter()
    for l in ls:
        base = l["id"]
        seen[base] += 1
        if seen[base] > 1:
            l["id"] = f"{base}-{seen[base]}"
    assert len({l["id"] for l in ls}) == 106
    for l in ls:
        if not (l.get("title") or "").strip():
            # legacy gap (page rendered "undefined"); synthesize from the row's own fields
            l["title"] = (l.get("org") or "").strip() + (" — " + l["posts"].strip() if l.get("posts") else "")
    for l in ls:
        dl = l.get("deadline") or ""
        assert not dl or re.fullmatch(r"\d{4}-\d{2}-\d{2}", dl), f"bad deadline {dl!r}"

    bank = {
        "exam": "sarkari-vacancies",
        "title": "Sarkari Job Vacancies",
        "updated": "2026-10-12",
        "questions": [], "capsules": [], "oneliners": [], "videos": [],
        "listings": ls, "pipeline": pipe, "directory": direc,
    }
    out = ROOT / "data" / "sarkari-vacancies.json"
    out.write_text(json.dumps(bank, ensure_ascii=False))
    print(f"  wrote {out} ({out.stat().st_size} bytes)")
    raw_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
