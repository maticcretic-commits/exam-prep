#!/usr/bin/env python3
"""Extractor for legacy software-ai-tech-prep (maticcretic-commits/software-ai-tech-prep).

Banks (established 2026-10-12 via the page's real parse path, node eval):
  1. assets/practice-bank.js -> window.PRACTICE_BANK: 705 {q,options,answer,explanation,topic}
     + 5 in-page wave scripts (var NEWQ -> B.push, real node eval of each IIFE): +36
     => 741 questions
  2. const quiz=[...] in index.html: 12 array-of-arrays [q,options,answer,expl] (mini-test)
  3. assets/topics-tech.js -> window.EPH_TOPIC_DATA: 10 topics, 50 {q,options,answer,expl}
  4. assets/oneliners.js -> window.ONELINERS: 350 strings
     + 5 wave scripts (var NEWC -> O.push): +42 => 392 one-liners
TOTAL questions = 803. No capsule/video JS banks (study chapters are HTML sections).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "maticcretic-commits/software-ai-tech-prep"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
LEGACY_URL = f"{RAW}/index.html"
ASSETS = {
    "practice-bank": f"{RAW}/assets/practice-bank.js",
    "oneliners": f"{RAW}/assets/oneliners.js",
    "topics-tech": f"{RAW}/assets/topics-tech.js",
}
EXPECTED = {"questions": 803, "oneliners": 392}

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const pbJs = fs.readFileSync(process.argv[2], 'utf8');
const olJs = fs.readFileSync(process.argv[3], 'utf8');
const ttJs = fs.readFileSync(process.argv[4], 'utf8');
global.window = {};
eval(pbJs);
eval(olJs);
// wave scripts: (function(){ var B = window.PRACTICE_BANK || []; var NEWQ=[...]; NEWQ.forEach(x=>B.push(x));
//                   var O = window.ONELINERS || [];  var NEWC=[...]; NEWC.forEach(x=>O.push(x)); })();
const waves = [...html.matchAll(/\(function\(\)\{\s*var B = window\.PRACTICE_BANK \|\| \[\];[\s\S]*?\}\)\(\);/g)].map(m => m[0]);
for (const w of waves) eval(w);
// const quiz=[ [q,options,answer,expl], ... ] — real JS parse path
const m = /(?:var|const|let)\s+quiz\s*=\s*\[/.exec(html);
if (!m) { console.error('no decl: quiz'); process.exit(1); }
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
const quiz = eval(html.slice(i, j + 1));
// topics-tech.js (study-topic library); stub document for its renderer guards
const elStub = () => ({ appendChild(){}, addEventListener(){}, set innerHTML(v){}, get innerHTML(){return ''},
  textContent:'', style:{}, classList:{add(){}}, dataset:{} });
global.document = { getElementById:() => elStub(), querySelector:() => elStub(),
  querySelectorAll:() => [], createElement:() => elStub() };
eval(ttJs);
const td = global.window.EPH_TOPIC_DATA;
process.stdout.write(JSON.stringify({
  waveBlocks: waves.length,
  bank: global.window.PRACTICE_BANK,
  oneliners: global.window.ONELINERS,
  quiz: quiz,
  topics: td.topics.map(t => ({ id: t.id, title: t.title, subject: t.subject, questions: t.questions || [] })),
}));
"""


def ensure_download(path: Path, url: str, min_size: int):
    if path.exists() and path.stat().st_size >= min_size:
        return
    subprocess.run(["curl", "-sL", "--max-time", "180", "-o", str(path), url], check=True)


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2a-software-ai-tech.html")
    pb_path = Path("/tmp/w2a-sat-practice-bank.js")
    ol_path = Path("/tmp/w2a-sat-oneliners.js")
    tt_path = Path("/tmp/w2a-sat-topics-tech.js")
    ensure_download(html_path, LEGACY_URL, 500_000)
    ensure_download(pb_path, ASSETS["practice-bank"], 100_000)
    ensure_download(ol_path, ASSETS["oneliners"], 10_000)
    ensure_download(tt_path, ASSETS["topics-tech"], 40_000)

    r = subprocess.run(
        ["node", "-e", NODE_EVAL, str(html_path), str(pb_path), str(ol_path), str(tt_path)],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed: {r.stderr[:600]}")
    parsed = json.loads(r.stdout)
    bank, oneliners, quiz, topics = parsed["bank"], parsed["oneliners"], parsed["quiz"], parsed["topics"]
    print(f"  wave blocks executed: {parsed['waveBlocks']}")
    tq = sum(len(t["questions"]) for t in topics)
    total = len(bank) + len(quiz) + tq
    print(f"  legacy: bank={len(bank)} quiz={len(quiz)} topicQs={tq} questions={total} (exp {EXPECTED['questions']}), oneliners={len(oneliners)} (exp {EXPECTED['oneliners']})")
    if total != EXPECTED["questions"] or len(oneliners) != EXPECTED["oneliners"] or parsed["waveBlocks"] != 5:
        print("COUNT MISMATCH — stopping, not writing data file.")
        return 1
    assert all(x is not None for x in bank), "null hole in bank"
    assert all(isinstance(x, str) for x in oneliners), "non-string oneliner"

    questions = []
    for x in bank:
        questions.append({
            "id": f"softtech-{len(questions) + 1:06d}",
            "exams": ["software-ai-tech"],
            "subject": (x.get("topic") or "General").strip(),
            "topic": "",
            "q": x["q"], "o": x["options"], "a": x["answer"],
            "e": x.get("explanation", "") or "",
            "source": "software-ai-tech-prep",
        })
    for row in quiz:
        questions.append({
            "id": f"softtech-{len(questions) + 1:06d}",
            "exams": ["software-ai-tech"],
            "subject": "General",
            "topic": "",
            "q": row[0], "o": row[1], "a": row[2],
            "e": row[3] if len(row) > 3 else "",
            "source": "software-ai-tech-prep",
        })
    for t in topics:
        for x in t["questions"]:
            questions.append({
                "id": f"softtech-{len(questions) + 1:06d}",
                "exams": ["software-ai-tech"],
                "subject": (t.get("subject") or "General").strip(),
                "topic": (t.get("title") or t.get("id") or "").strip(),
                "q": x["q"], "o": x["options"], "a": x["answer"],
                "e": x.get("expl", "") or "",
                "source": "software-ai-tech-prep",
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

    ol = [{"id": f"softtech-ol-{i + 1:06d}", "subject": "", "text": t} for i, t in enumerate(oneliners)]
    assert "Muse" not in json.dumps({"q": questions, "o": ol}), "Muse mention found"

    data = {
        "exam": "software-ai-tech",
        "title": "Software, AI & Tech Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": ol,
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "software-ai-tech.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes) — self-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
