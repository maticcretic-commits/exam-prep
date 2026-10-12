#!/usr/bin/env python3
"""Extractor for legacy defence-prep (maticcretic-commits/defence-prep).

The page serves THREE question systems; all extracted with the real parse path:
  1. var quiz = [...] in index.html .............. 105 {q,o,a,e} (mock-test section)
  2. window.EPH_TOPIC_DATA from assets/topics-defence.js (base 558) + the 6
     in-page "Wave" scripts that append ADD[t.id] per topic (real node eval of
     each IIFE, exactly as the browser runs them) -> 808 {q,options,answer,expl}
  3. EPH_TOPIC_DATA.papers ....................... 80 mock-paper questions
TOTAL questions = 993. No oneliner/capsule/video JS banks exist on the page.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "maticcretic-commits/defence-prep"
LEGACY_URL = f"https://raw.githubusercontent.com/{REPO}/main/index.html"
TOPICS_URL = f"https://raw.githubusercontent.com/{REPO}/main/assets/topics-defence.js"
EXPECTED = {"questions": 993}

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const topicsJs = fs.readFileSync(process.argv[2], 'utf8');

// --- bank 1: flat `var quiz=[...]` in index.html (real JS parse path) ---
function evalArray(name) {
  const m = new RegExp('(?:var|const|let)\\s+' + name + '\\s*=\\s*\\[').exec(html);
  if (!m) { console.error('no decl: ' + name); process.exit(1); }
  let i = m.index + m[0].length - 1, depth = 0, inStr = null, esc = false, j = i;
  while (j < html.length) {
    const c = html[j];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === inStr) inStr = null;
    } else {
      if (c === '"' || c === "'") inStr = c;
      else if (c === '[') depth++;
      else if (c === ']') { depth--; if (depth === 0) break; }
    }
    j++;
  }
  if (depth !== 0) { console.error('unbalanced: ' + name); process.exit(1); }
  return eval(html.slice(i, j + 1));
}
const quiz = evalArray('quiz');

// --- banks 2+3: EPH_TOPIC_DATA base + wave appends, as the browser does ---
global.window = {};
eval(topicsJs);
const waves = [...html.matchAll(/\(function\(\)\{\s*var D = window\.EPH_TOPIC_DATA;[\s\S]*?\}\)\(\);/g)].map(m => m[0]);
for (const w of waves) eval(w);
const D = global.window.EPH_TOPIC_DATA;

process.stdout.write(JSON.stringify({
  quiz: quiz,
  waveBlocks: waves.length,
  topics: D.topics.map(t => ({ id: t.id, title: t.title, subject: t.subject, questions: t.questions || [] })),
  papers: (D.papers || []).map(p => ({ id: p.id, title: p.title, questions: p.questions || [] })),
}));
"""


def ensure_download(path: Path, url: str, min_size: int):
    if path.exists() and path.stat().st_size >= min_size:
        return
    subprocess.run(["curl", "-sL", "--max-time", "180", "-o", str(path), url], check=True)


def check_question(item: dict, idx: int):
    assert isinstance(item.get("q"), str) and item["q"].strip(), f"bad q at {idx}"
    assert isinstance(item.get("o"), list) and len(item["o"]) >= 2, f"bad o at {idx}"
    assert all(isinstance(x, str) and x.strip() for x in item["o"]), f"bad option at {idx}"
    a = item.get("a")
    assert isinstance(a, int) and 0 <= a < len(item["o"]), f"bad a at {idx}"
    for k in ("subject", "topic", "e", "source"):
        assert isinstance(item.get(k), str), f"bad {k} at {idx}"
    assert re.fullmatch(r"[a-z]+-\d{6}", item["id"]), f"bad id at {idx}"


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2a-defence.html")
    topics_path = Path("/tmp/w2a-defence-topics.js")
    ensure_download(html_path, LEGACY_URL, 1_000_000)
    ensure_download(topics_path, TOPICS_URL, 50_000)
    print(f"legacy: {html_path} ({html_path.stat().st_size} b) + {topics_path} ({topics_path.stat().st_size} b)")

    r = subprocess.run(
        ["node", "-e", NODE_EVAL, str(html_path), str(topics_path)],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed: {r.stderr[:600]}")
    parsed = json.loads(r.stdout)
    quiz, topics, papers = parsed["quiz"], parsed["topics"], parsed["papers"]
    print(f"  wave blocks executed: {parsed['waveBlocks']}")
    tq = sum(len(t["questions"]) for t in topics)
    pq = sum(len(p["questions"]) for p in papers)
    total = len(quiz) + tq + pq
    print(f"  legacy counts: quiz={len(quiz)} topicQs={tq} paperQs={pq} total={total} (expected {EXPECTED['questions']})")
    if total != EXPECTED["questions"] or parsed["waveBlocks"] != 6:
        print("COUNT MISMATCH — stopping, not writing data file.")
        return 1
    assert all(x is not None for x in quiz), "null hole in quiz"
    for t in topics:
        assert all(x is not None for x in t["questions"]), f"null hole in topic {t['id']}"

    questions = []
    for x in quiz:
        questions.append({
            "id": f"defence-{len(questions) + 1:06d}",
            "exams": ["defence"],
            "subject": "General",
            "topic": "",
            "q": x["q"], "o": x["o"], "a": x["a"],
            "e": x.get("e", "") or "",
            "source": "defence-prep",
        })
    for t in topics:
        for x in t["questions"]:
            questions.append({
                "id": f"defence-{len(questions) + 1:06d}",
                "exams": ["defence"],
                "subject": (t.get("subject") or "General").strip(),
                "topic": (t.get("title") or t.get("id") or "").strip(),
                "q": x["q"], "o": x["options"], "a": x["answer"],
                "e": x.get("expl", "") or "",
                "source": "defence-prep",
            })
    for p in papers:
        for x in p["questions"]:
            questions.append({
                "id": f"defence-{len(questions) + 1:06d}",
                "exams": ["defence"],
                "subject": "Mock Paper",
                "topic": (p.get("title") or p.get("id") or "").strip(),
                "q": x["q"], "o": x["options"], "a": x["answer"],
                "e": x.get("expl", "") or "",
                "source": "defence-prep",
            })

    for idx, item in enumerate(questions):
        check_question(item, idx)
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert "Muse" not in json.dumps(questions), "Muse mention found"

    data = {
        "exam": "defence",
        "title": "Defence Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "defence.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes) — self-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
