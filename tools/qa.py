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
    "ssc": {
        "questions": 923,
        "oneliners": 459,
        "capsules": 414
    },
    "pte": {
        "questions": 635,
        "oneliners": 15,
        "capsules": 13
    },
    "toefl": {
        "questions": 721,
        "oneliners": 18,
        "capsules": 21
    },
    "gre": {
        "questions": 638,
        "oneliners": 13,
        "capsules": 13
    },
    "gmat": {
        "questions": 641,
        "oneliners": 12,
        "capsules": 11
    },
    "sat": {
        "questions": 649,
        "oneliners": 15,
        "capsules": 12
    },
    "ielts": {
        "questions": 672,
        "oneliners": 23,
        "capsules": 22,
        "resources": 100
    },
    "railways": {
        "questions": 1009,
        "capsules": 39,
        "oneliners": 37
    },
    "law": {
        "questions": 828,
        "capsules": 217,
        "oneliners": 327
    },
    "neet": {
        "questions": 1109,
        "oneliners": 439,
        "capsules": 43
    },
    "bpsc": {
        "questions": 2010,
        "capsules": 1034,
        "oneliners": 952
    },
    "banking-certs": {
        "questions": 2187,
        "oneliners": 1119,
        "capsules": 321,
        "videos": 48
    },
    "upsc": {
        "questions": 1096,
        "oneliners": 52,
        "capsules": 60
    },
    "jee": {
        "questions": 1194,
        "oneliners": 374,
        "capsules": 29
    },
    "banking": {
        "questions": 958,
        "capsules": 91,
        "oneliners": 47
    },
    "defence": {
        "questions": 1081,
        "capsules": 54,
        "oneliners": 39
    },
    "current-affairs": {
        "questions": 874,
        "oneliners": 97,
        "capsules": 105
    },
    "software-ai-tech": {
        "questions": 886,
        "oneliners": 426,
        "capsules": 59
    },
    "teaching": {
        "questions": 824,
        "capsules": 46,
        "oneliners": 28
    },
    "ca": {
        "questions": 965,
        "oneliners": 33,
        "capsules": 44
    },
    "sarkari-vacancies": {
        "questions": 8,
        "oneliners": 7,
        "capsules": 10,
        "videos": 0,
        "listings": 191
    }
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


def check_video(v: dict, i: int, seen: set):
    tag = f"videos[{i}]"
    if v.get("id") in seen:
        fail(f"{tag}: duplicate id {v.get('id')}")
    seen.add(v.get("id"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", v.get("youtube_id") or ""):
        fail(f"{tag}: bad youtube_id {v.get('youtube_id')!r}")
    if not (v.get("title") or "").strip():
        fail(f"{tag}: empty title")
    if not isinstance(v.get("subject"), str):
        fail(f"{tag}: subject must be string")


def check_listing(l: dict, i: int, seen: set):
    tag = f"listings[{i}]"
    if not isinstance(l.get("id"), str) or not l["id"]:
        fail(f"{tag}: bad id {l.get('id')!r}")
    if l.get("id") in seen:
        fail(f"{tag}: duplicate id {l.get('id')}")
    seen.add(l.get("id"))
    if not (l.get("title") or "").strip():
        fail(f"{tag}: empty title")
    if not (l.get("org") or "").strip():
        fail(f"{tag}: empty org")
    if l.get("deadline") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", l["deadline"]):
        fail(f"{tag}: bad deadline {l.get('deadline')!r}")


def check_resource(r: dict, i: int, seen: set):
    tag = f"resources[{i}]"
    if r.get("id") in seen:
        fail(f"{tag}: duplicate id {r.get('id')}")
    seen.add(r.get("id"))
    if not isinstance(r.get("subject"), str):
        fail(f"{tag}: subject must be string")
    if not (r.get("title") or "").strip():
        fail(f"{tag}: empty title")
    if not (r.get("body") or "").strip():
        fail(f"{tag}: empty body")


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
        for k in ("questions", "capsules", "oneliners", "videos"):
            if not isinstance(b.get(k), list):
                fail(f"{slug}: top-level {k} must be a list")
        for k in ("listings", "resources", "pipeline", "directory"):
            if k in b and not isinstance(b[k], list):
                fail(f"{slug}: top-level {k} must be a list")
        sq, sc, so, sv, sl, sr = set(), set(), set(), set(), set(), set()
        for i, q in enumerate(b.get("questions", [])):
            check_question(q, i, sq)
        for i, c in enumerate(b.get("capsules", [])):
            check_capsule(c, i, sc)
        for i, o in enumerate(b.get("oneliners", [])):
            check_oneliner(o, i, so)
        for i, v in enumerate(b.get("videos", [])):
            check_video(v, i, sv)
        for i, l in enumerate(b.get("listings", [])):
            check_listing(l, i, sl)
        for i, r in enumerate(b.get("resources", [])):
            check_resource(r, i, sr)
        if not any(f.startswith("questions[") or f.startswith("capsules[") or f.startswith("oneliners[") for f in FAILURES):
            ok(f"{slug}: all {len(b['questions'])}q/{len(b['oneliners'])}ol/{len(b['capsules'])}cap/{len(b.get('videos', []))}vid/{len(b.get('listings', []))}list/{len(b.get('resources', []))}res items valid")

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
        for mname, dkey in (("video-count", "videos"), ("listing-count", "listings"), ("resource-count", "resources")):
            mm = re.search(r'<meta name="' + mname + r'" content="(\d+)">', html)
            want = len(b.get(dkey, []))
            if not mm or int(mm.group(1)) != want:
                fail(f"exam/{slug}: meta {mname} {mm.group(1) if mm else None} != data {want}")
            else:
                ok(f"exam/{slug}: meta {mname} matches data ({want})")
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
