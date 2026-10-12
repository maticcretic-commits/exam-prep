#!/usr/bin/env python3
"""Extractor for legacy bpsc-prep (maticcretic-commits/bpsc-prep).

Reads the FULL raw index.html, parses the banks with the page's REAL parse
path — JSON.parse(document.getElementById(id).textContent) for each
application/json script block, concatenated exactly as the page does — and
emits data/bpsc.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (established 2026-10-12 via the real parse path):
  QUIZ = quiz-data + quiz-data-new + quiz-data-new2 = 1902 questions
         {id, question, options, answer_index, explanation, category,
          difficulty, date, [capsule_id]}
  ONES = oneliners-data + oneliners-data-new + oneliners-data-new2 = 907
         {id, category, date, text}
  CAPS = capsules-data + capsules-data-new + capsules-data-new2 = 987
         {id, date, category, title, capsule, tags, bihar_relevant, high_yield}

Answer-key finding: `answer_index` (int, 0-based) — verified 0 out of 1902
out of range. Legacy ids (Q-####, Q-NEW-####, Q-NEW#-####, ...) do NOT match
[a-z]+-\\d{6}, so unified ids bpsc-000001... are generated.
NOTE: 24 legacy ids are shared by 2 DIFFERENT questions (id collisions
between the -new blocks); the live page concats them all, and so do we —
unified ids are sequential so no collision carries over.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

BLOCKS = {
    "quiz": ["quiz-data", "quiz-data-new", "quiz-data-new2"],
    "oneliners": ["oneliners-data", "oneliners-data-new", "oneliners-data-new2"],
    "capsules": ["capsules-data", "capsules-data-new", "capsules-data-new2"],
}
EXPECTED = {"quiz": 1902, "oneliners": 907, "capsules": 987}

NODE_JSONBLOCK = r"""
// the page's real parse path: JSON.parse(document.getElementById(id).textContent)
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const ids = process.argv[2].split(',');
let out = [];
for (const id of ids) {
  const m = new RegExp('<script[^>]*id="' + id + '"[^>]*>([\\s\\S]*?)</script>').exec(html);
  if (!m) { console.error('no block: ' + id); process.exit(1); }
  out = out.concat(JSON.parse(m[1]));  // page does parse(a).concat(parse(b), parse(c))
}
process.stdout.write(JSON.stringify(out));
"""


def node_blocks(html_path: Path, ids):
    r = subprocess.run(
        ["node", "-e", NODE_JSONBLOCK, str(html_path), ",".join(ids)],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed for {ids}: {r.stderr[:500]}")
    return json.loads(r.stdout)


def check_item(x: dict):
    assert x["q"] and isinstance(x["q"], str), "empty q"
    assert isinstance(x["o"], list) and len(x["o"]) >= 2, "options < 2"
    assert all(isinstance(o, str) and o.strip() for o in x["o"]), "empty option"
    assert isinstance(x["a"], int) and 0 <= x["a"] < len(x["o"]), "answer out of range"
    for k in ("subject", "topic", "module", "e", "difficulty"):
        assert isinstance(x[k], str), f"{k} not str"


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2b-bpsc-prep.html")
    html = html_path.read_text(errors="replace")
    print(f"legacy file: {html_path} ({len(html)} bytes)")

    banks = {k: node_blocks(html_path, v) for k, v in BLOCKS.items()}
    for label, want in EXPECTED.items():
        got = len(banks[label])
        status = "OK" if got == want else "MISMATCH"
        print(f"  legacy {label}: {got} (expected {want}) [{status}]")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
    assert all(x is not None for x in banks["quiz"]), "null hole in quiz"

    questions = []
    for x in banks["quiz"]:
        a = x.get("answer_index")
        assert isinstance(a, int) and 0 <= a < len(x["options"]), \
            f"bad answer_index on {x.get('id')}"
        questions.append({
            "id": f"bpsc-{len(questions) + 1:06d}",
            "exams": ["bpsc"],
            "subject": (x.get("category") or "").strip(),
            "module": "",
            "topic": "",
            "difficulty": (x.get("difficulty") or "").strip(),
            "q": x["question"],
            "o": x["options"],
            "a": a,
            "e": x.get("explanation", ""),
            "source": "bpsc-prep",
        })
    for x in questions:
        check_item(x)
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", i) for i in ids), "bad id shape"

    oneliners = [
        {
            "id": f"bpsc-ol-{i + 1:06d}",
            "subject": (x.get("category") or "").strip(),
            "text": x["text"],
        }
        for i, x in enumerate(banks["oneliners"])
    ]
    assert all(o["text"].strip() for o in oneliners), "empty oneliner text"

    capsules = [
        {
            "id": f"bpsc-cap-{i + 1:06d}",
            "subject": (x.get("category") or "").strip(),
            "title": x.get("title", ""),
            "body": x.get("capsule", ""),
        }
        for i, x in enumerate(banks["capsules"])
    ]
    assert all(c["title"].strip() and c["body"].strip() for c in capsules), "empty capsule"

    data = {
        "exam": "bpsc",
        "title": "BPSC Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": capsules,
        "oneliners": oneliners,
        "videos": [],
        "listings": [],
    }
    blob = json.dumps(data, ensure_ascii=False)
    assert not re.search(r"\bMuse\b", blob), "'Muse' mention in content"
    for key in ("exam", "title", "updated", "questions", "capsules",
                "oneliners", "videos", "listings"):
        assert key in data, f"missing top-level key {key}"
    out = root / "data" / "bpsc.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  questions={len(questions)} oneliners={len(oneliners)} capsules={len(capsules)}")
    print("SELF-CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
