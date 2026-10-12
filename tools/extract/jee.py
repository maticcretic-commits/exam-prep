#!/usr/bin/env python3
"""Extractor for legacy jee-prep (maticcretic-commits/jee-prep).

Multi-file bank. Downloads (or reuses) the FULL raw asset files via curl,
parses them with the page's REAL parse path — node eval of the bank literals
in the page's load order, as the browser evaluates them — and emits
data/jee.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy shape (established 2026-10-12 via node eval of the real literals):
  assets/mcq-bank-jee.js -> window.JEE_MCQ_BANK = [{q, options, answer, explanation, topic}]
  assets/oneliners-jee.js -> window.JEE_ONELINERS = [350 strings]
  assets/topics-jee.js    -> window.EPH_TOPIC_DATA {exam, examName, topics:[12], papers:[2]}
  assets/topics.js        -> shared renderer (NOT a bank)

Fresh legacy counts (node eval, 2026-10-12 ~23:45 IST):
  JEE_MCQ_BANK = 974  (file header comment says 963 — stale; real count wins)
  JEE_ONELINERS = 350 (all strings)
  EPH topics   = 12 topics / 60 questions (Physics 20, Chemistry 20, Mathematics 20)
  EPH papers   = 2 papers / 80 questions
  TOTAL questions = 974 + 60 + 80 = 1114

  Topic study sections (intro/tables/inline-SVG diagrams) have NO home in the
  unified schema -> NOT migrated; flagged in the worker report.
  Image audit: ZERO <img> tags and ZERO assets/*.png|jpg|svg references in any
  bank file; index.html's 22 <img> tags are page chrome (base64 data-URI hero
  art, remote thumbs), not bank content.
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "maticcretic-commits/jee-prep"
EXPECTED = {"mcq": 974, "oneliners": 350, "eph_topics": 12, "eph_tq": 60, "eph_pq": 80}

NODE_EVAL = r"""
const fs = require('fs');
const files = JSON.parse(process.argv[1]);
global.window = {};
eval(fs.readFileSync(files[0], 'utf8'));   // window.JEE_MCQ_BANK
eval(fs.readFileSync(files[1], 'utf8'));   // window.JEE_ONELINERS
eval(fs.readFileSync(files[2], 'utf8'));   // window.EPH_TOPIC_DATA
process.stdout.write(JSON.stringify({
  mcq: global.window.JEE_MCQ_BANK,
  oneliners: global.window.JEE_ONELINERS,
  eph: global.window.EPH_TOPIC_DATA,
}));
"""


def download(paths):
    base = f"https://raw.githubusercontent.com/{REPO}/main/assets"
    for name, path in zip(["mcq-bank-jee.js", "oneliners-jee.js", "topics-jee.js"], paths):
        if not path.exists():
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(f"{base}/{name}", path)


def split_topic(tv):
    """'Physics – Rotational Mechanics' -> ('Physics', 'Physics – Rotational Mechanics')."""
    tv = str(tv or "")
    for sep in (" – ", " · "):
        if sep in tv:
            return tv.split(sep, 1)[0].strip(), tv.strip()
    return tv.strip(), ""


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    dl = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w3")
    paths = [dl / f"w3-jee-{n}" for n in ["mcq-bank-jee.js", "oneliners-jee.js", "topics-jee.js"]]
    download(paths)
    for p in paths:
        print(f"  {p.name}: {p.stat().st_size} bytes")

    r = subprocess.run(
        ["node", "-e", NODE_EVAL, json.dumps([str(p) for p in paths])],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed: {r.stderr[:500]}")
    parsed = json.loads(r.stdout)

    # ---- legacy counts FIRST ----
    mcq, oneliners, eph = parsed["mcq"], parsed["oneliners"], parsed["eph"]
    assert eph and isinstance(eph.get("topics"), list), "no EPH topics"
    eph_tq = sum(len(t.get("questions", [])) for t in eph["topics"])
    eph_pq = sum(len(p.get("questions", [])) for p in eph.get("papers", []))
    checks = [
        ("mcq", len(mcq), EXPECTED["mcq"]),
        ("oneliners", len(oneliners), EXPECTED["oneliners"]),
        ("eph_topics", len(eph["topics"]), EXPECTED["eph_topics"]),
        ("eph_topic_q", eph_tq, EXPECTED["eph_tq"]),
        ("eph_paper_q", eph_pq, EXPECTED["eph_pq"]),
    ]
    for label, got, want in checks:
        status = "OK" if got == want else "MISMATCH"
        print(f"  legacy {label}: {got} (expected {want}) [{status}]")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
    legacy_total = len(mcq) + eph_tq + eph_pq
    print(f"legacy total questions = {legacy_total}")

    # ---- map ----
    questions = []
    n = 0

    def add(q, o, a, e, subject, module, topic):
        global_n = len(questions) + 1
        assert isinstance(q, str) and q.strip(), "empty q"
        assert isinstance(o, list) and len(o) >= 2 and all(
            isinstance(x, str) and x.strip() for x in o), "bad options"
        assert isinstance(a, int) and 0 <= a < len(o), "bad answer"
        questions.append({
            "id": f"jee-{global_n:06d}",
            "exams": ["jee"],
            "subject": subject,
            "module": module,
            "topic": topic,
            "difficulty": "",
            "q": q,
            "o": o,
            "a": a,
            "e": e,
            "source": "jee-prep",
        })

    for m in mcq:
        assert m is not None, "null hole in JEE_MCQ_BANK"
        subj, top = split_topic(m.get("topic", ""))
        add(m["q"], m["options"], m["answer"], str(m.get("explanation", "") or ""),
            subj, "", top)
    for t in eph["topics"]:
        for m in t.get("questions", []):
            assert m is not None, "null hole in EPH topic questions"
            add(m["q"], m["options"], m["answer"], str(m.get("expl", "") or ""),
                str(t.get("subject", "") or ""), str(t.get("tag", "") or ""),
                str(t.get("title", "") or ""))
    for p in eph.get("papers", []):
        for m in p.get("questions", []):
            assert m is not None, "null hole in EPH paper questions"
            add(m["q"], m["options"], m["answer"], str(m.get("expl", "") or ""),
                "Practice Paper", "", str(p.get("title", "") or ""))
    if len(questions) != legacy_total:
        print(f"EXTRACTED {len(questions)} != LEGACY {legacy_total} — stopping.")
        return 1

    ol = []
    for i, t in enumerate(oneliners):
        assert isinstance(t, str) and t.strip(), "empty/non-string oneliner"
        ol.append({"id": f"jee-ol-{i + 1:06d}", "subject": "", "text": t})
    assert len(ol) == EXPECTED["oneliners"]

    data = {
        "exam": "jee",
        "title": "JEE Main + Advanced",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": ol,
        "videos": [],
        "listings": [],
    }
    blob = json.dumps(data, ensure_ascii=False, indent=1)
    assert "Muse" not in blob, "forbidden token in output"
    out = root / "data" / "jee.json"
    out.write_text(blob)

    # ---- self-check ----
    back = json.loads(out.read_text())
    assert set(back.keys()) == {"exam", "title", "updated", "questions", "capsules",
                                "oneliners", "videos", "listings"}, "top-level keys"
    assert len(back["questions"]) == legacy_total
    assert len(back["oneliners"]) == EXPECTED["oneliners"]
    ids = [it["id"] for it in back["questions"]]
    assert len(ids) == len(set(ids)) and ids == sorted(ids), "id uniqueness/order"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", i) for i in ids), "id shape"
    for it in back["questions"]:
        assert it["q"].strip() and len(it["o"]) >= 2 and 0 <= it["a"] < len(it["o"])
        assert isinstance(it["subject"], str) and it["subject"]
    for it in back["oneliners"]:
        assert it["text"].strip()
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"SELF-CHECK PASS: questions={len(back['questions'])} "
          f"oneliners={len(back['oneliners'])} ids-unique={len(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
