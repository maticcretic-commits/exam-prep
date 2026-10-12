#!/usr/bin/env python3
"""Extractor for legacy law-prep (maticcretic-commits/law-prep).

Reads the FULL raw index.html, parses the banks with the page's REAL parse
path (browser-equivalent JS evaluation via node — the legacy literals use
JS-only \\' escapes), and emits data/law.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (established 2026-10-12 via node eval of the real literals):
  window.LAW_BANK     = 637 questions {q, options, answer, explanation, topic?}
  var quiz            = 108 questions {q, a:[options], c:correct, e} for 71 items
                          + {q, o:[options], a:correct, e} for 37 items (quiz-card widget)
  window.LAW_ONELINERS = 300 one-liners (plain strings)
  window.LAW_CAPSULES  = 169 capsules {d:date, t:title, x:body}
Zero q-text overlap between quiz and LAW_BANK — both migrated, no dedupe.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

EXPECTED = {"bank": 637, "quiz": 108, "oneliners": 300, "capsules": 169}
TOTAL_Q = EXPECTED["bank"] + EXPECTED["quiz"]

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const name = process.argv[2];
const decl = name.startsWith('window.')
  ? 'window\\.' + name.slice(7) + '\\s*=\\s*\\['
  : '(?:var|const|let)\\s+' + name + '\\s*=\\s*\\[';
const m = new RegExp(decl).exec(html);
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


def check_item(x: dict):
    assert x["q"] and isinstance(x["q"], str), "empty q"
    assert isinstance(x["o"], list) and len(x["o"]) >= 2, "options < 2"
    assert all(isinstance(o, str) and o.strip() for o in x["o"]), "empty option"
    assert isinstance(x["a"], int) and 0 <= x["a"] < len(x["o"]), "answer out of range"
    for k in ("subject", "topic", "module", "e"):
        assert isinstance(x[k], str), f"{k} not str"


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2b-law-prep.html")
    html = html_path.read_text(errors="replace")
    print(f"legacy file: {html_path} ({len(html)} bytes)")

    lbank = js_parse(html_path, "window.LAW_BANK")
    lquiz = js_parse(html_path, "quiz")
    lonel = js_parse(html_path, "window.LAW_ONELINERS")
    lcaps = js_parse(html_path, "window.LAW_CAPSULES")

    for label, got, want in [("LAW_BANK", len(lbank), EXPECTED["bank"]),
                             ("quiz", len(lquiz), EXPECTED["quiz"]),
                             ("LAW_ONELINERS", len(lonel), EXPECTED["oneliners"]),
                             ("LAW_CAPSULES", len(lcaps), EXPECTED["capsules"])]:
        status = "OK" if got == want else "MISMATCH"
        print(f"  legacy {label}: {got} (expected {want}) [{status}]")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
    assert all(x is not None for x in lbank + lquiz + lcaps), "null hole in banks"
    assert all(isinstance(t, str) and t.strip() for t in lonel), "bad oneliner"

    bank_qs = {x["q"] for x in lbank}
    overlap = sum(1 for x in lquiz if x["q"] in bank_qs)
    print(f"  q-text overlap LAW_BANK/quiz: {overlap}")
    assert overlap == 0, "unexpected overlap — dedupe decision needed"

    questions = []
    for x in lbank:
        t = (x.get("topic") or "").strip()
        if ": " in t:
            subject, topic = t.split(": ", 1)
        elif t:
            subject, topic = t, ""
        else:
            subject, topic = "", ""
        questions.append({
            "id": f"law-{len(questions) + 1:06d}",
            "exams": ["law"],
            "subject": subject.strip(),
            "module": "",
            "topic": topic.strip(),
            "difficulty": "",
            "q": x["q"],
            "o": x["options"],
            "a": x["answer"],
            "e": x.get("explanation", ""),
            "source": "law-prep",
        })
    for x in lquiz:  # legacy: {q, a:options, c:correct index, e} OR {q, o:options, a:correct, e}
        if "c" in x:
            opts, ans = x["a"], x["c"]
        else:
            opts, ans = x["o"], x["a"]
        questions.append({
            "id": f"law-{len(questions) + 1:06d}",
            "exams": ["law"],
            "subject": "",
            "module": "Quiz",
            "topic": "",
            "difficulty": "",
            "q": x["q"],
            "o": opts,
            "a": ans,
            "e": x.get("e", ""),
            "source": "law-prep",
        })

    assert len(questions) == TOTAL_Q, f"extracted {len(questions)} != legacy {TOTAL_Q}"
    for x in questions:
        check_item(x)
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", i) for i in ids), "bad id shape"

    oneliners = [
        {"id": f"law-ol-{i + 1:06d}", "subject": "", "text": t}
        for i, t in enumerate(lonel)
    ]
    assert all(o["text"].strip() for o in oneliners), "empty oneliner text"

    capsules = [
        {
            "id": f"law-cap-{i + 1:06d}",
            "subject": "",
            "title": x.get("t", ""),
            "body": x.get("x", ""),
        }
        for i, x in enumerate(lcaps)
    ]
    assert all(c["title"].strip() and c["body"].strip() for c in capsules), "empty capsule"

    data = {
        "exam": "law",
        "title": "Law Entrance Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": capsules,
        "oneliners": oneliners,
        "videos": [],
        "listings": [],
    }
    blob = json.dumps(data, ensure_ascii=False)
    assert not re.search(r"\bMuse\b", blob), "'Muse' mention in content"
    out = root / "data" / "law.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  questions={len(questions)} oneliners={len(oneliners)} capsules={len(capsules)}")
    print("SELF-CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
