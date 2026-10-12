#!/usr/bin/env python3
"""Extractor for legacy banking-prep (maticcretic-commits/banking-prep).

Banks (established 2026-10-12 via the page's real JS parse path, node eval):
  quiz      = 854 questions  {s,q,o,a,e}          -> questions[]
  quant     = 15 study cards [topic,line1,line2]  -> capsules[]
  reasoning = 10 study cards {t,b,k}              -> capsules[]
  english   = 10 study cards {t,b,k}              -> capsules[]
(items/trend are DOM-derived, not content banks.)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/maticcretic-commits/banking-prep/main/index.html"
# 854 top-level items, BUT item index 672 has a refresh-append junction corruption
# (the known `},,`/missing-`]` bug class): 7 complete {s,q,o,a,e} questions were
# appended INSIDE item 672's options array instead of as new top-level elements.
# The page renders them as "[object Object]" options — genuinely broken live.
# Repair (lossless, deterministic): item 672 keeps its 4 string options and the
# 7 nested dicts are promoted to standalone questions in legacy order.
# Extracted questions = 854 + 7 = 861.
EXPECTED = {"questions": 861, "capsules": 35, "oneliners": 0, "videos": 0}

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
    subprocess.run(
        ["curl", "-sL", "--max-time", "180", "-o", str(path), LEGACY_URL], check=True
    )


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
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2a-banking.html")
    ensure_download(html_path)
    print(f"legacy file: {html_path} ({html_path.stat().st_size} bytes)")

    quiz = js_parse(html_path, "quiz")
    quant = js_parse(html_path, "quant")
    reasoning = js_parse(html_path, "reasoning")
    english = js_parse(html_path, "english")

    # --- junction-corruption repair (see EXPECTED comment above) ---
    flat = []
    nested_found = 0
    for i, x in enumerate(quiz):
        opts, nested = [], []
        for v in x["o"]:
            (nested if isinstance(v, dict) else opts).append(v)
        if nested:
            nested_found += 1
            assert i == 672, f"unexpected nested-dict junction at item {i}"
            for d in nested:
                assert set(("s", "q", "o", "a")) <= set(d), f"nested dict missing keys at {i}"
                assert isinstance(d["o"], list) and all(isinstance(s, str) and s.strip() for s in d["o"]), f"bad nested options at {i}"
                assert isinstance(d["a"], int) and 0 <= d["a"] < len(d["o"]), f"bad nested answer at {i}"
                assert isinstance(d["q"], str) and d["q"].strip(), f"bad nested q at {i}"
            flat.append({**x, "o": opts})
            flat.extend(nested)
        else:
            flat.append(x)
    assert nested_found == 1 and len([v for x in flat for v in x["o"] if not isinstance(v, str)]) == 0
    assert len(flat) == EXPECTED["questions"], f"repair count {len(flat)} != {EXPECTED['questions']}"
    quiz = flat

    assert all(x is not None for x in quiz), "null hole in quiz"
    assert all(x is not None for x in quant + reasoning + english), "null hole in capsules"

    for label, got, want in [
        ("questions", len(quiz), EXPECTED["questions"]),
        ("capsules", len(quant) + len(reasoning) + len(english), EXPECTED["capsules"]),
    ]:
        print(f"  legacy {label}: {got} (expected {want})")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1

    questions = [
        {
            "id": f"banking-{i + 1:06d}",
            "exams": ["banking"],
            "subject": (x.get("s") or "General").strip(),
            "topic": "",
            "q": x["q"],
            "o": x["o"],
            "a": x["a"],
            "e": x.get("e", "") or "",
            "source": "banking-prep",
        }
        for i, x in enumerate(quiz)
    ]

    caps = []
    for i, row in enumerate(quant):
        caps.append({
            "id": f"banking-cap-{i + 1:06d}",
            "subject": "Quantitative Aptitude",
            "title": row[0],
            "body": "<p>" + "</p><p>".join(row[1:]) + "</p>",
        })
    for i, x in enumerate(reasoning):
        body = "<p>" + x.get("b", "") + "</p>"
        if x.get("k"):
            body += "<ul>" + "".join(f"<li>{k}</li>" for k in x["k"]) + "</ul>"
        caps.append({
            "id": f"banking-cap-{len(quant) + i + 1:06d}",
            "subject": "Reasoning",
            "title": x.get("t", ""),
            "body": body,
        })
    for i, x in enumerate(english):
        body = "<p>" + x.get("b", "") + "</p>"
        if x.get("k"):
            body += "<ul>" + "".join(f"<li>{k}</li>" for k in x["k"]) + "</ul>"
        caps.append({
            "id": f"banking-cap-{len(quant) + len(reasoning) + i + 1:06d}",
            "subject": "English",
            "title": x.get("t", ""),
            "body": body,
        })

    for idx, item in enumerate(questions):
        check_question(item, idx)
    ids = [x["id"] for x in questions] + [x["id"] for x in caps]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert "Muse" not in json.dumps({"q": questions, "c": caps}), "Muse mention found"

    data = {
        "exam": "banking",
        "title": "Banking Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": caps,
        "oneliners": [],
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "banking.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  questions={len(questions)} capsules={len(caps)} — self-check PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
