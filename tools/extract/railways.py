#!/usr/bin/env python3
"""Extractor for legacy railways-prep (maticcretic-commits/railways-prep).

Reads the FULL raw index.html, parses the two question banks with the page's
REAL parse path (browser-equivalent JS evaluation via node — the legacy
literals use JS-only quoting), and emits data/railways.json in the unified
schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (established 2026-10-12 via node eval of the real literals):
  var BANK = 826 questions {q, options, answer, explanation, topic}
  var quiz = 103 questions {q, o, a, e}  (interactive "Practice test" panel)
Zero q-text overlap between the two banks — both are migrated, no dedupe.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

EXPECTED = {"bank": 826, "quiz": 103}
TOTAL = EXPECTED["bank"] + EXPECTED["quiz"]

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


def split_topic(t: str):
    """'Maths — Percentage' / 'Railways - current affairs' -> (subject, topic)."""
    for sep in (" — ", " - "):
        if sep in t:
            s, top = t.split(sep, 1)
            return s.strip(), top.strip()
    return (t.strip(), "") if t.strip() else ("", "")


def check_item(x: dict):
    assert x["q"] and isinstance(x["q"], str), "empty q"
    assert isinstance(x["o"], list) and len(x["o"]) >= 2, "options < 2"
    assert all(isinstance(o, str) and o.strip() for o in x["o"]), "empty option"
    assert isinstance(x["a"], int) and 0 <= x["a"] < len(x["o"]), "answer out of range"
    for k in ("subject", "topic", "module", "e"):
        assert isinstance(x[k], str), f"{k} not str"


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2b-railways-prep.html")
    html = html_path.read_text(errors="replace")
    print(f"legacy file: {html_path} ({len(html)} bytes)")

    bank = js_parse(html_path, "BANK")
    quiz = js_parse(html_path, "quiz")

    for label, got, want in [("bank", len(bank), EXPECTED["bank"]),
                             ("quiz", len(quiz), EXPECTED["quiz"])]:
        status = "OK" if got == want else "MISMATCH"
        print(f"  legacy {label}: {got} (expected {want}) [{status}]")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
    assert all(x is not None for x in bank + quiz), "null hole in banks"

    # overlap check: q-text shared between banks?
    bank_qs = {x["q"] for x in bank}
    overlap = sum(1 for x in quiz if x["q"] in bank_qs)
    print(f"  q-text overlap bank/quiz: {overlap}")
    assert overlap == 0, "unexpected overlap — dedupe decision needed"

    questions = []
    for x in bank:
        subject, topic = split_topic(x.get("topic", ""))
        questions.append({
            "id": f"railways-{len(questions) + 1:06d}",
            "exams": ["railways"],
            "subject": subject,
            "module": "",
            "topic": topic,
            "difficulty": "",
            "q": x["q"],
            "o": x["options"],
            "a": x["answer"],
            "e": x.get("explanation", ""),
            "source": "railways-prep",
        })
    for x in quiz:
        questions.append({
            "id": f"railways-{len(questions) + 1:06d}",
            "exams": ["railways"],
            "subject": "",
            "module": "Practice test",
            "topic": "",
            "difficulty": "",
            "q": x["q"],
            "o": x["o"],
            "a": x["a"],
            "e": x.get("e", ""),
            "source": "railways-prep",
        })

    assert len(questions) == TOTAL, f"extracted {len(questions)} != legacy {TOTAL}"
    for x in questions:
        check_item(x)
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", i) for i in ids), "bad id shape"
    blob = json.dumps(questions, ensure_ascii=False)
    assert not re.search(r"\bMuse\b", blob), "'Muse' mention in content"

    data = {
        "exam": "railways",
        "title": "Railways Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "railways.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  questions={len(questions)} (bank={EXPECTED['bank']} quiz={EXPECTED['quiz']})")
    print("SELF-CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
