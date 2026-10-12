#!/usr/bin/env python3
"""Extractor for legacy teaching-prep (maticcretic-commits/teaching-prep).

Banks (established 2026-10-12 via the page's real parse path, node eval):
  var questions=[...] (158) + 4 in-page `questions=questions.concat([...])`
  refresh appends (real node eval of each statement, in document order) => 748
  questions {t,q,o,a,w,e} — w/e are mutually exclusive explanation fields.
  var examData={p1,p2,tre} (exam-pattern info cards) => 3 capsules.
No oneliner/video JS banks (one-liners are plain HTML <li> lists).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/maticcretic-commits/teaching-prep/main/index.html"
EXPECTED = {"questions": 748, "capsules": 3}

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
function bracketLiteral(startIdx, open, close) {
  let i = startIdx, depth = 0, inStr = null, esc = false, j = i;
  while (j < html.length) {
    const c = html[j];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === inStr) inStr = null;
    } else {
      if (c === '"' || c === "'") inStr = c;
      else if (c === open) depth++;
      else if (c === close) { depth--; if (depth === 0) break; }
    }
    j++;
  }
  if (depth !== 0) { console.error('unbalanced'); process.exit(1); }
  return html.slice(i, j + 1);
}
// base: var questions=[...] — real JS parse path
const m = /(?:var|const|let)\s+questions\s*=\s*\[/.exec(html);
if (!m) { console.error('no decl: questions'); process.exit(1); }
let questions = eval(bracketLiteral(m.index + m[0].length - 1, '[', ']'));
// refresh waves: questions=questions.concat([...]); — eval each in document order
const concats = [...html.matchAll(/questions\s*=\s*questions\.concat\(\[[\s\S]*?\]\);?/g)].map(x => x[0]);
for (const c of concats) questions = eval('questions.concat(' + c.replace(/^.*?\.concat\(/, '').replace(/\);?\s*$/, '') + ')');
// var examData={...} — object literal, real JS parse path
const m2 = /var examData=\{/.exec(html);
const examData = eval('(' + bracketLiteral(m2.index + m2[0].length - 1, '{', '}') + ')');
process.stdout.write(JSON.stringify({ base: 158, concats: concats.length, questions: questions, examData: examData }));
"""


def ensure_download(path: Path):
    if path.exists() and path.stat().st_size > 100_000:
        return
    subprocess.run(["curl", "-sL", "--max-time", "180", "-o", str(path), LEGACY_URL], check=True)


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2a-teaching.html")
    ensure_download(html_path)
    print(f"legacy file: {html_path} ({html_path.stat().st_size} bytes)")

    r = subprocess.run(["node", "-e", NODE_EVAL, str(html_path)],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed: {r.stderr[:600]}")
    parsed = json.loads(r.stdout)
    bank, exam_data = parsed["questions"], parsed["examData"]
    print(f"  concat blocks executed: {parsed['concats']}")
    print(f"  legacy questions: {len(bank)} (expected {EXPECTED['questions']}), examData sections: {len(exam_data)} (expected {EXPECTED['capsules']})")
    if len(bank) != EXPECTED["questions"] or len(exam_data) != EXPECTED["capsules"]:
        print("COUNT MISMATCH — stopping, not writing data file.")
        return 1
    assert all(x is not None for x in bank), "null hole in questions"

    questions = []
    for i, x in enumerate(bank):
        t = (x.get("t") or "").strip()
        if "·" in t:
            subject, topic = [p.strip() for p in t.split("·", 1)]
        else:
            subject, topic = t or "General", ""
        item = {
            "id": f"teaching-{i + 1:06d}",
            "exams": ["teaching"],
            "subject": subject or "General",
            "topic": topic,
            "q": x["q"],
            "o": x["o"],
            "a": x["a"],
            "e": (x.get("e") or "") or (x.get("w") or ""),
            "source": "teaching-prep",
        }
        assert isinstance(item["q"], str) and item["q"].strip(), f"bad q at {i}"
        assert isinstance(item["o"], list) and len(item["o"]) >= 2, f"bad o at {i}"
        assert all(isinstance(s, str) and s.strip() for s in item["o"]), f"bad option at {i}"
        assert isinstance(item["a"], int) and 0 <= item["a"] < len(item["o"]), f"bad a at {i}"
        assert re.fullmatch(r"[a-z]+-\d{6}", item["id"]), f"bad id at {i}"
        questions.append(item)
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"

    caps = []
    for i, (key, sec) in enumerate(exam_data.items()):
        body = f"<p>{sec.get('desc', '')}</p>"
        if sec.get("facts"):
            body += "<ul>" + "".join(f"<li><b>{f[0]}:</b> {f[1]}</li>" for f in sec["facts"]) + "</ul>"
        if sec.get("papers"):
            body += "<ul>" + "".join(f"<li><b>{p[0]}:</b> {p[1]}</li>" for p in sec["papers"]) + "</ul>"
        caps.append({
            "id": f"teaching-cap-{i + 1:06d}",
            "subject": "Exam Pattern",
            "title": sec.get("title", key),
            "body": body,
        })
    assert "Muse" not in json.dumps({"q": questions, "c": caps}), "Muse mention found"

    data = {
        "exam": "teaching",
        "title": "Teaching Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": caps,
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "teaching.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes) — self-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
