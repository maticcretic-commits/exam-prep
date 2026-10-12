#!/usr/bin/env python3
"""Extractor for legacy upsc-prep (maticcretic-commits/upsc-prep).

Multi-file bank. Downloads (or reuses) the FULL raw asset files via curl,
parses them with the page's REAL parse path — node eval of the four bank
files in the page's exact load order, replicating how topics.js consumes
window.EPH_TOPIC_DATA — and emits data/upsc.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy shape (established 2026-10-12 via node eval of the real load order):
  assets/topics-upsc.js   -> creates window.EPH_TOPIC_DATA {exam, examName, topics:[1], papers:[]}
  assets/topics-upsc-2.js -> topics.push(17); papers = [2 practice papers x 50 q]
  assets/topics-upsc-3.js -> topics.push(13)   ("expansion question bank")
  assets/topics-upsc-4.js -> topics.push(11)   ("Wave 2 expansion question bank")
  assets/topics.js        -> shared renderer (NOT a bank)

Fresh legacy counts (node eval, 2026-10-12 ~23:40 IST):
  file 1:  1 topic,   5 questions
  file 2: 17 topics, 85 questions + 2 papers x 50 = 100 paper questions
  file 3: 13 topics, 600 questions
  file 4: 11 topics, 207 questions
  TOTAL: 42 topics, 997 questions (897 topic + 100 paper)

  Topic contract: {id, title, subject, tag, blurb, intro,
                   sections:[{h, body?, table?, svg?}], questions:[{q, options[4], answer, expl}]}
  Paper contract: {id, title, meta, minutes, instructions, questions:[{q, options, answer, expl}]}

  Topic study sections (intro/tables/inline-SVG diagrams) have NO home in the
  unified schema -> NOT migrated; flagged in the worker report.
  Image audit: ZERO <img> tags in any question/section HTML; diagrams are inline
  SVG; index.html images are base64 data-URI hero art + remote (wikimedia /
  i.ytimg.com) thumbs — page chrome, not bank content. No assets/*.png|jpg|svg
  references exist anywhere in the repo working tree.
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = "maticcretic-commits/upsc-prep"
BANK_FILES = ["topics-upsc.js", "topics-upsc-2.js", "topics-upsc-3.js", "topics-upsc-4.js"]
EXPECTED_TOPICS = [1, 17, 13, 11]
EXPECTED_Q = [5, 85, 600, 207]
EXPECTED_PAPER_Q = 100  # file 2 also ships 2 x 50-question practice papers

NODE_EVAL = r"""
const fs = require('fs');
const files = JSON.parse(process.argv[1]);
global.window = {};
let prevTopics = 0;
const perFile = [];
for (const f of files) {
  eval(fs.readFileSync(f, 'utf8'));   // real parse path: the page's load order
  const D = global.window.EPH_TOPIC_DATA;
  if (!D || !Array.isArray(D.topics)) { console.error('no EPH_TOPIC_DATA.topics after ' + f); process.exit(1); }
  let q = 0;
  for (let i = prevTopics; i < D.topics.length; i++) q += (D.topics[i].questions || []).length;
  perFile.push({file: f, topics: D.topics.length - prevTopics, questions: q,
                newTopics: D.topics.slice(prevTopics)});
  prevTopics = D.topics.length;
}
process.stdout.write(JSON.stringify({perFile, papers: global.window.EPH_TOPIC_DATA.papers || []}));
"""


def download(paths):
    base = f"https://raw.githubusercontent.com/{REPO}/main/assets"
    for name, path in zip(BANK_FILES, paths):
        if not path.exists():
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(f"{base}/{name}", path)


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    dl = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w3")
    paths = [dl / f"w3-upsc-{n}" for n in BANK_FILES]
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

    # ---- legacy counts per FILE first ----
    legacy_total = 0
    for i, pf in enumerate(parsed["perFile"]):
        got_t, got_q = pf["topics"], pf["questions"]
        want_t, want_q = EXPECTED_TOPICS[i], EXPECTED_Q[i]
        status = "OK" if (got_t, got_q) == (want_t, want_q) else "MISMATCH"
        print(f"  legacy {pf['file']}: topics={got_t} (exp {want_t}) "
              f"questions={got_q} (exp {want_q}) [{status}]")
        if (got_t, got_q) != (want_t, want_q):
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
        legacy_total += got_q
    papers = parsed["papers"]
    paper_q = sum(len(p.get("questions", [])) for p in papers)
    print(f"  legacy papers: {len(papers)} files' worth, paper questions={paper_q} (exp {EXPECTED_PAPER_Q})")
    if paper_q != EXPECTED_PAPER_Q:
        print("PAPER COUNT MISMATCH — stopping.")
        return 1
    legacy_total += paper_q
    print(f"legacy total questions = {legacy_total}")

    # ---- map ----
    questions = []
    n = 0
    for pf in parsed["perFile"]:
        for t in pf["newTopics"]:
            subj = str(t.get("subject", "") or "")
            for m in t.get("questions", []):
                assert m is not None, "null hole in topic questions"
                q, o, a = m.get("q"), m.get("options"), m.get("answer")
                assert isinstance(q, str) and q.strip(), "empty q"
                assert isinstance(o, list) and len(o) >= 2 and all(
                    isinstance(x, str) and x.strip() for x in o), "bad options"
                assert isinstance(a, int) and 0 <= a < len(o), "bad answer"
                n += 1
                questions.append({
                    "id": f"upsc-{n:06d}",
                    "exams": ["upsc"],
                    "subject": subj,
                    "module": str(t.get("tag", "") or ""),
                    "topic": str(t.get("title", "") or ""),
                    "difficulty": "",
                    "q": q,
                    "o": o,
                    "a": a,
                    "e": str(m.get("expl", "") or ""),
                    "source": "upsc-prep",
                })
    for p in papers:
        for m in p.get("questions", []):
            assert m is not None, "null hole in paper questions"
            q, o, a = m.get("q"), m.get("options"), m.get("answer")
            assert isinstance(q, str) and q.strip(), "empty paper q"
            assert isinstance(o, list) and len(o) >= 2 and all(
                isinstance(x, str) and x.strip() for x in o), "bad paper options"
            assert isinstance(a, int) and 0 <= a < len(o), "bad paper answer"
            n += 1
            questions.append({
                "id": f"upsc-{n:06d}",
                "exams": ["upsc"],
                "subject": "Practice Paper",
                "module": "",
                "topic": str(p.get("title", "") or ""),
                "difficulty": "",
                "q": q,
                "o": o,
                "a": a,
                "e": str(m.get("expl", "") or ""),
                "source": "upsc-prep",
            })
    if len(questions) != legacy_total:
        print(f"EXTRACTED {len(questions)} != LEGACY {legacy_total} — stopping.")
        return 1

    data = {
        "exam": "upsc",
        "title": "UPSC Civil Services",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    blob = json.dumps(data, ensure_ascii=False, indent=1)
    assert "Muse" not in blob, "forbidden token in output"
    out = root / "data" / "upsc.json"
    out.write_text(blob)

    # ---- self-check ----
    back = json.loads(out.read_text())
    assert set(back.keys()) == {"exam", "title", "updated", "questions", "capsules",
                                "oneliners", "videos", "listings"}, "top-level keys"
    assert len(back["questions"]) == legacy_total
    ids = [it["id"] for it in back["questions"]]
    assert len(ids) == len(set(ids)), "duplicate ids"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", i) for i in ids), "id shape"
    assert ids == sorted(ids), "ids not sequential"
    for it in back["questions"]:
        assert it["q"].strip() and len(it["o"]) >= 2 and 0 <= it["a"] < len(it["o"])
        assert isinstance(it["subject"], str) and it["subject"]
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"SELF-CHECK PASS: questions={len(back['questions'])} ids-unique={len(ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
