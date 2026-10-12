#!/usr/bin/env python3
"""Extractor for legacy ca-prep (maticcretic-commits/ca-prep).

Banks (established 2026-10-12 via the page's real parse path):
  1. <script type="application/json" id="ca-mcq-bank"> — the page's own
     `JSON.parse(document.getElementById('ca-mcq-bank').textContent)` path:
     750 {q,options,answer,explanation,topic}
  2. assets/topics-ca.js -> window.EPH_TOPIC_DATA (node eval of the asset,
     same as the browser): 10 topics, 50 {q,options,answer,expl} questions
  3. EPH_TOPIC_DATA.papers: 2 mock papers, 80 questions
TOTAL questions = 880. No oneliner/capsule/video JS banks (recall cards/notes are HTML).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "maticcretic-commits/ca-prep"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
LEGACY_URL = f"{RAW}/index.html"
TOPICS_URL = f"{RAW}/assets/topics-ca.js"
EXPECTED = {"questions": 880}

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const topicsJs = fs.readFileSync(process.argv[2], 'utf8');
// bank 1: exactly the page's parse path
const m = /<script type="application\/json" id="ca-mcq-bank">([\s\S]*?)<\/script>/.exec(html);
if (!m) { console.error('no ca-mcq-bank blob'); process.exit(1); }
const bank = JSON.parse(m[1]);
// banks 2+3: asset eval as the browser does
global.window = {};
eval(topicsJs);
const D = global.window.EPH_TOPIC_DATA;
process.stdout.write(JSON.stringify({
  bank: bank,
  topics: D.topics.map(t => ({ id: t.id, title: t.title, subject: t.subject, questions: t.questions || [] })),
  papers: (D.papers || []).map(p => ({ id: p.id, title: p.title, questions: p.questions || [] })),
}));
"""


def ensure_download(path: Path, url: str, min_size: int):
    if path.exists() and path.stat().st_size >= min_size:
        return
    subprocess.run(["curl", "-sL", "--max-time", "180", "-o", str(path), url], check=True)


def split_topic(t: str):
    t = (t or "").strip()
    if ": " in t:
        s, top = t.split(": ", 1)
        return s.strip() or "General", top.strip()
    return t or "General", ""


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2a-ca.html")
    topics_path = Path("/tmp/w2a-ca-topics.js")
    ensure_download(html_path, LEGACY_URL, 1_000_000)
    ensure_download(topics_path, TOPICS_URL, 40_000)
    print(f"legacy: {html_path} ({html_path.stat().st_size} b) + {topics_path} ({topics_path.stat().st_size} b)")

    r = subprocess.run(["node", "-e", NODE_EVAL, str(html_path), str(topics_path)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed: {r.stderr[:600]}")
    parsed = json.loads(r.stdout)
    bank, topics, papers = parsed["bank"], parsed["topics"], parsed["papers"]
    tq = sum(len(t["questions"]) for t in topics)
    pq = sum(len(p["questions"]) for p in papers)
    total = len(bank) + tq + pq
    print(f"  legacy: mcq-bank={len(bank)} topicQs={tq} paperQs={pq} total={total} (expected {EXPECTED['questions']})")
    if total != EXPECTED["questions"]:
        print("COUNT MISMATCH — stopping, not writing data file.")
        return 1
    assert all(x is not None for x in bank), "null hole in mcq-bank"

    questions = []
    for x in bank:
        subject, topic = split_topic(x.get("topic", ""))
        questions.append({
            "id": f"ca-{len(questions) + 1:06d}",
            "exams": ["ca"],
            "subject": subject,
            "topic": topic,
            "q": x["q"], "o": x["options"], "a": x["answer"],
            "e": x.get("explanation", "") or "",
            "source": "ca-prep",
        })
    for t in topics:
        for x in t["questions"]:
            questions.append({
                "id": f"ca-{len(questions) + 1:06d}",
                "exams": ["ca"],
                "subject": (t.get("subject") or "General").strip(),
                "topic": (t.get("title") or t.get("id") or "").strip(),
                "q": x["q"], "o": x["options"], "a": x["answer"],
                "e": x.get("expl", "") or "",
                "source": "ca-prep",
            })
    for p in papers:
        for x in p["questions"]:
            questions.append({
                "id": f"ca-{len(questions) + 1:06d}",
                "exams": ["ca"],
                "subject": "Mock Paper",
                "topic": (p.get("title") or p.get("id") or "").strip(),
                "q": x["q"], "o": x["options"], "a": x["answer"],
                "e": x.get("expl", "") or "",
                "source": "ca-prep",
            })

    for idx, item in enumerate(questions):
        assert isinstance(item["q"], str) and item["q"].strip(), f"bad q at {idx}"
        assert isinstance(item["o"], list) and len(item["o"]) >= 2, f"bad o at {idx}"
        assert all(isinstance(s, str) and s.strip() for s in item["o"]), f"bad option at {idx}"
        assert isinstance(item["a"], int) and 0 <= item["a"] < len(item["o"]), f"bad a at {idx}"
        for k in ("subject", "topic", "e", "source"):
            assert isinstance(item[k], str), f"bad {k} at {idx}"
        assert re.fullmatch(r"[a-z]+-\d{6}", item["id"]), f"bad id at {idx}"
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert "Muse" not in json.dumps(questions), "Muse mention found"

    data = {
        "exam": "ca",
        "title": "CA Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "ca.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes) — self-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
