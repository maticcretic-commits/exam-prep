#!/usr/bin/env python3
"""Extractor for legacy pte-prep (maticcretic-commits/pte-prep).

Reads the FULL raw index.html, parses the bank with the page's REAL parse path
(browser-equivalent JS evaluation via node — the legacy literals may contain
JS-only backslash-quote escapes that are invalid JSON but valid JS), and emits
data/pte.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (established 2026-10-12 via node eval of the real literal):
  QUESTIONS = 574 questions {s,q,o,a,e}
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/maticcretic-commits/pte-prep/main/index.html"
BANK_VAR = "QUESTIONS"
EXPECTED_QUESTIONS = 574

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
const arr = eval(html.slice(i, j + 1));
process.stdout.write(JSON.stringify(arr));
"""


def js_parse(html_path, var_name):
    r = subprocess.run(
        ["node", "-e", NODE_EVAL, str(html_path), var_name],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError("node parse failed for %s: %s" % (var_name, r.stderr[:500]))
    return json.loads(r.stdout)


ID_RE = re.compile(r"^[a-z]+-\d{6}$")


def check_question(q, idx):
    assert isinstance(q.get("id"), str) and ID_RE.match(q["id"]), "q[%d] bad id" % idx
    assert q["exams"] == ["pte"], "q[%d] bad exams" % idx
    assert isinstance(q.get("subject"), str) and q["subject"], "q[%d] bad subject" % idx
    assert isinstance(q.get("topic"), str), "q[%d] bad topic" % idx
    assert isinstance(q.get("q"), str) and q["q"], "q[%d] bad q" % idx
    o = q.get("o")
    assert isinstance(o, list) and len(o) >= 2 and all(isinstance(s, str) and s for s in o), "q[%d] bad o" % idx
    a = q.get("a")
    assert isinstance(a, int) and 0 <= a < len(o), "q[%d] bad a" % idx
    assert isinstance(q.get("e"), str), "q[%d] bad e" % idx
    assert isinstance(q.get("source"), str) and q["source"], "q[%d] bad source" % idx
    assert "muse" not in json.dumps(q).lower().replace("museum", ""), "q[%d] Muse mention" % idx


def main():
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w1-pte.html")
    html = html_path.read_text(errors="replace")
    print("legacy file: %s (%d bytes)" % (html_path, len(html)))

    bank = js_parse(html_path, BANK_VAR)
    assert all(x is not None for x in bank), "null hole in bank"
    legacy_n = len(bank)
    print("  legacy %s: %d (expected %d)" % (BANK_VAR, legacy_n, EXPECTED_QUESTIONS))
    if legacy_n != EXPECTED_QUESTIONS:
        print("COUNT MISMATCH vs pre-scan -- stopping, not writing data file.")
        return 1

    questions = []
    for i, x in enumerate(bank):
        questions.append({
            "id": "pte-%06d" % (i + 1),
            "exams": ["pte"],
            "subject": (x.get("s") or "General").strip(),
            "topic": "",
            "q": x["q"],
            "o": x["o"],
            "a": x["a"],
            "e": x.get("e") or "",
            "source": "pte-prep",
        })

    assert len(questions) == legacy_n, "extracted != legacy"
    ids = [q["id"] for q in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    for i, q in enumerate(questions):
        check_question(q, i)

    listings = []

    data = {
        "exam": "pte",
        "title": "PTE Academic Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": [],
        "videos": [],
        "listings": listings,
    }
    out = root / "data" / "pte.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print("wrote %s (%d bytes)" % (out, out.stat().st_size))
    print("  questions=%d capsules=0 oneliners=0 videos=0 listings=%d"
          % (len(questions), len(listings)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
