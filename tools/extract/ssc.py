#!/usr/bin/env python3
"""Extractor for legacy ssc-prep (maticcretic-commits/ssc-prep).

Reads the FULL raw index.html, parses the three banks with the page's REAL
parse path (browser-equivalent JS evaluation via node — the legacy literals
contain JS-only \\' escapes that are invalid JSON but valid JS, exactly the
bug class that silently emptied banks before), and emits data/ssc.json in the
unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (established 2026-10-12 via node eval of the real literals):
  SSC_QBANK     = 826 questions  {q,o,a,e} + t(topic) or s(subject)
  SSC_ONELINERS = 400 one-liners (plain strings)
  SSC_CAPSULES  = 366 capsules   {t:title, g:group, x:body}
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/maticcretic-commits/ssc-prep/main/index.html"
EXPECTED = {"questions": 826, "oneliners": 400, "capsules": 366}

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
    """Parse a legacy `var NAME=[...]` with the real JS parse path. Returns the array."""
    r = subprocess.run(
        ["node", "-e", NODE_EVAL, str(html_path), var_name],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed for {var_name}: {r.stderr[:500]}")
    return json.loads(r.stdout)


def map_question(x: dict, i: int) -> dict:
    # legacy: {q, o, a, e} + t("Subject: Topic" or bare) or s(subject)
    t = x.get("t", "")
    s = x.get("s", "")
    if s:
        subject, topic = s.title(), (t or "")
    elif ": " in t:
        subject, topic = t.split(": ", 1)
    elif t:
        subject, topic = t, ""
    else:
        subject, topic = "General", ""
    item = {
        "id": f"ssc-{i + 1:06d}",
        "exams": ["ssc"],
        "subject": subject.strip(),
        "topic": topic.strip(),
        "q": x["q"],
        "o": x["o"],
        "a": x["a"],
        "e": x.get("e", ""),
        "source": "ssc-prep",
    }
    return item


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/ssc-fresh.html")
    html = html_path.read_text(errors="replace")
    print(f"legacy file: {html_path} ({len(html)} bytes)")

    qbank = js_parse(html_path, "SSC_QBANK")
    oneliners = js_parse(html_path, "SSC_ONELINERS")
    capsules = js_parse(html_path, "SSC_CAPSULES")

    # QA gate 1: exact count match with legacy (real parse path)
    for label, got, want in [
        ("questions", len(qbank), EXPECTED["questions"]),
        ("oneliners", len(oneliners), EXPECTED["oneliners"]),
        ("capsules", len(capsules), EXPECTED["capsules"]),
    ]:
        status = "OK" if got == want else "MISMATCH"
        print(f"  legacy {label}: {got} (expected {want}) [{status}]")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
    # no silent holes
    assert all(x is not None for x in qbank), "null hole in qbank"
    assert all(isinstance(x, str) for x in oneliners), "non-string oneliner"
    assert all(x is not None for x in capsules), "null hole in capsules"

    questions = [map_question(x, i) for i, x in enumerate(qbank)]
    ol = [
        {"id": f"ssc-ol-{i + 1:06d}", "subject": "", "text": t}
        for i, t in enumerate(oneliners)
    ]
    caps = [
        {
            "id": f"ssc-cap-{i + 1:06d}",
            "subject": (x.get("g") or "").strip(),
            "title": x.get("t", ""),
            "body": x.get("x", ""),
        }
        for i, x in enumerate(capsules)
    ]

    data = {
        "exam": "ssc",
        "title": "SSC Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": caps,
        "oneliners": ol,
        "videos": [],
        "listings": [],
    }
    out = root / "data" / "ssc.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  questions={len(questions)} oneliners={len(ol)} capsules={len(caps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
