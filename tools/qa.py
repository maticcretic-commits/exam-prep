#!/usr/bin/env python3
"""ExamPrep migration QA gate. Every exam, no exceptions.

Gates:
  1. Bank counts in data/<slug>.json EXACTLY equal legacy counts.
  2. Every item validates against the unified schema.
  3. Generated exam page exists, references the right assets/data,
     and its embedded counts equal the data counts (render check).
  4. engine.js passes node --check.
  5. data/*.json and meta.json parse cleanly.

Exit 0 = all gates pass. Anything else = stop, do not push.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# legacy counts established via the page's real parse path (node eval)
EXPECTED = {
    "ssc": {"questions": 826, "oneliners": 400, "capsules": 366},
    "pte": {"questions": 574, "oneliners": 0, "capsules": 0},
    "toefl": {"questions": 653, "oneliners": 0, "capsules": 0},
    "gre": {"questions": 576, "oneliners": 0, "capsules": 0},
    "gmat": {"questions": 583, "oneliners": 0, "capsules": 0},
    "sat": {"questions": 593, "oneliners": 0, "capsules": 0},
    "ielts": {"questions": 601, "oneliners": 0, "capsules": 0},
    "railways": {"questions": 929, "oneliners": 0, "capsules": 0},
    "law": {"questions": 745, "oneliners": 300, "capsules": 169},
    "neet": {"questions": 1026, "oneliners": 409, "capsules": 0},
    "bpsc": {"questions": 1926, "oneliners": 907, "capsules": 987},
    "banking-certs": {"questions": 2119, "oneliners": 1097, "capsules": 292},
    "upsc": {"questions": 997, "oneliners": 0, "capsules": 0},
    "jee": {"questions": 1114, "oneliners": 350, "capsules": 0},
    "banking": {"questions": 861, "oneliners": 0, "capsules": 35},
    "defence": {"questions": 993, "oneliners": 0, "capsules": 0},
    "current-affairs": {"questions": 751, "oneliners": 0, "capsules": 0},
    "software-ai-tech": {"questions": 803, "oneliners": 392, "capsules": 0},
    "teaching": {"questions": 748, "oneliners": 0, "capsules": 3},
    "ca": {"questions": 880, "oneliners": 0, "capsules": 0},
}

FAILURES = []


def fail(msg: str):
    FAILURES.append(msg)
    print(f"  FAIL: {msg}")


def ok(msg: str):
    print(f"  ok: {msg}")


def check_question(q: dict, i: int, seen: set):
    tag = f"questions[{i}]"
    if not isinstance(q.get("id"), str) or not re.fullmatch(r"[a-z]+-\d{6}", q["id"]):
        fail(f"{tag}: bad id {q.get('id')!r}")
    if q.get("id") in seen:
        fail(f"{tag}: duplicate id {q.get('id')}")
    seen.add(q.get("id"))
    if not isinstance(q.get("exams"), list) or not q["exams"] or not all(isinstance(e, str) for e in q["exams"]):
        fail(f"{tag}: exams must be non-empty string list")
    for k in ("subject", "topic", "q", "e", "source"):
        if not isinstance(q.get(k), str):
            fail(f"{tag}: {k} must be string")
    if not q.get("q", "").strip():
        fail(f"{tag}: empty question text")
    o = q.get("o")
    if not isinstance(o, list) or len(o) < 2 or not all(isinstance(x, str) and x.strip() for x in o):
        fail(f"{tag}: o must be >=2 non-empty strings")
    a = q.get("a")
    if not isinstance(a, int) or isinstance(a, bool) or not (0 <= a < len(o or [])):
        fail(f"{tag}: answer index {a!r} out of range for {len(o or [])} options")


def check_capsule(c: dict, i: int, seen: set):
    tag = f"capsules[{i}]"
    if c.get("id") in seen:
        fail(f"{tag}: duplicate id {c.get('id')}")
    seen.add(c.get("id"))
    if not isinstance(c.get("subject"), str):
        fail(f"{tag}: subject must be string")
    if not (c.get("title") or "").strip():
        fail(f"{tag}: empty title")
    if not (c.get("body") or "").strip():
        fail(f"{tag}: empty body")


def check_oneliner(o: dict, i: int, seen: set):
    tag = f"oneliners[{i}]"
    if o.get("id") in seen:
        fail(f"{tag}: duplicate id {o.get('id')}")
    seen.add(o.get("id"))
    if not isinstance(o.get("subject"), str):
        fail(f"{tag}: subject must be string")
    if not (o.get("text") or "").strip():
        fail(f"{tag}: empty text")


def main() -> int:
    print("== gate 1: data files parse ==")
    try:
        meta = json.loads((ROOT / "data" / "meta.json").read_text())
        ok("meta.json parses")
    except Exception as e:
        fail(f"meta.json parse: {e}")
        meta = None
    banks = {}
    for slug in EXPECTED:
        try:
            banks[slug] = json.loads((ROOT / "data" / f"{slug}.json").read_text())
            ok(f"data/{slug}.json parses")
        except Exception as e:
            fail(f"data/{slug}.json parse: {e}")

    print("== gate 2: exact count match vs legacy ==")
    for slug, exp in EXPECTED.items():
        b = banks.get(slug)
        if not b:
            continue
        for k, want in exp.items():
            got = len(b.get(k, []))
            if got == want:
                ok(f"{slug}.{k}: {got} == legacy {want}")
            else:
                fail(f"{slug}.{k}: {got} != legacy {want}")

    print("== gate 3: schema validation ==")
    for slug, b in banks.items():
        for k in ("exam", "title", "updated"):
            if not isinstance(b.get(k), str) or not b[k]:
                fail(f"{slug}: top-level {k} missing/empty")
        for k in ("questions", "capsules", "oneliners", "videos", "listings"):
            if not isinstance(b.get(k), list):
                fail(f"{slug}: top-level {k} must be a list")
        sq, sc, so = set(), set(), set()
        for i, q in enumerate(b.get("questions", [])):
            check_question(q, i, sq)
        for i, c in enumerate(b.get("capsules", [])):
            check_capsule(c, i, sc)
        for i, o in enumerate(b.get("oneliners", [])):
            check_oneliner(o, i, so)
        if not any(f.startswith("questions[") or f.startswith("capsules[") or f.startswith("oneliners[") for f in FAILURES):
            ok(f"{slug}: all {len(b['questions'])}q/{len(b['oneliners'])}ol/{len(b['capsules'])}cap items valid")

    print("== gate 4: render check (generated pages) ==")
    for slug, b in banks.items():
        page = ROOT / "exam" / slug / "index.html"
        if not page.exists():
            fail(f"exam/{slug}/index.html missing — run tools/build.py")
            continue
        html = page.read_text()
        for needle in ('../../assets/engine.js', '../../assets/style.css', f"data-exam=\"{slug}\""):
            if needle not in html:
                fail(f"exam/{slug}/index.html missing {needle}")
        m = re.search(r'<meta name="question-count" content="(\d+)">', html)
        if not m or int(m.group(1)) != len(b["questions"]):
            fail(f"exam/{slug}: meta question-count {m.group(1) if m else None} != data {len(b['questions'])}")
        else:
            ok(f"exam/{slug}/index.html references assets + count meta matches data ({m.group(1)})")
        eng = (ROOT / "assets" / "engine.js").read_text()
        if "'../../data/'" not in eng or ".json" not in eng or "fetch(" not in eng:
            fail("engine.js does not fetch the per-exam data JSON")
    landing = ROOT / "index.html"
    if not landing.exists():
        fail("index.html missing — run tools/build.py")
    elif meta and all(f'exam/{e["slug"]}/' in landing.read_text() for e in meta["exams"]):
        ok("index.html links all registered exams")

    print("== gate 5: engine syntax ==")
    r = subprocess.run(["node", "--check", str(ROOT / "assets" / "engine.js")],
                       capture_output=True, text=True)
    if r.returncode == 0:
        ok("assets/engine.js passes node --check")
    else:
        fail(f"engine.js syntax: {r.stderr[:300]}")

    print()
    if FAILURES:
        print(f"QA GATE: {len(FAILURES)} FAILURE(S) — do not push.")
        return 1
    print("QA GATE: ALL PASS — safe to push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
