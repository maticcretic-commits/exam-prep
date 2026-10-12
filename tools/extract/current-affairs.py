#!/usr/bin/env python3
"""Extractor for legacy current-affairs-exams (maticcretic-commits/current-affairs-exams).

Banks (established 2026-10-12 via the page's real JS parse path, node eval):
  QUIZ = 751 questions {q,o,a,e,t}  -> questions[]
No wave appends, no oneliner/capsule/video JS banks (items/trend are DOM-derived).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/maticcretic-commits/current-affairs-exams/main/index.html"
EXPECTED = {"questions": 751}

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const name = process.argv[2];
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
const arr = eval(html.slice(i, j + 1));  // real JS parse path, as the browser does
process.stdout.write(JSON.stringify(arr));
"""


def js_parse(html_path: Path, var_name: str):
    r = subprocess.run(
        ["node", "-e", NODE_EVAL, str(html_path), var_name],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed for {var_name}: {r.stderr[:500]}")
    return json.loads(r.stdout)


def ensure_download(path: Path):
    if path.exists() and path.stat().st_size > 100_000:
        return
    subprocess.run(["curl", "-sL", "--max-time", "180", "-o", str(path), LEGACY_URL], check=True)


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2a-current-affairs.html")
    ensure_download(html_path)
    print(f"legacy file: {html_path} ({html_path.stat().st_size} bytes)")

    bank = js_parse(html_path, "QUIZ")
    assert all(x is not None for x in bank), "null hole in QUIZ"
    print(f"  legacy questions: {len(bank)} (expected {EXPECTED['questions']})")
    if len(bank) != EXPECTED["questions"]:
        print("COUNT MISMATCH — stopping, not writing data file.")
        return 1

    questions = []
    for i, x in enumerate(bank):
        item = {
            "id": f"curraff-{i + 1:06d}",
            "exams": ["current-affairs"],
            "subject": (x.get("t") or "General").strip(),
            "topic": "",
            "q": x["q"],
            "o": x["o"],
            "a": x["a"],
            "e": x.get("e", "") or "",
            "source": "current-affairs-exams",
        }
        assert isinstance(item["q"], str) and item["q"].strip(), f"bad q at {i}"
        assert isinstance(item["o"], list) and len(item["o"]) >= 2, f"bad o at {i}"
        assert all(isinstance(s, str) and s.strip() for s in item["o"]), f"bad option at {i}"
        assert isinstance(item["a"], int) and 0 <= item["a"] < len(item["o"]), f"bad a at {i}"
        assert re.fullmatch(r"[a-z]+-\d{6}", item["id"]), f"bad id at {i}"
        questions.append(item)

    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert "Muse" not in json.dumps(questions), "Muse mention found"

    data = {
        "exam": "current-affairs",
        "title": "Current Affairs",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "current-affairs.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes) — self-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
