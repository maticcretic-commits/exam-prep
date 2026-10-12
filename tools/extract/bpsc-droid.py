#!/usr/bin/env python3
"""Extractor for the droid-account BPSC PCS daily MCQs (niteshlhsnda-droid/bpsc-pcs-prep).

Reads the FULL raw index.html, parses BPSC_DAILY_MCQS with the page's REAL
parse path (browser-equivalent JS evaluation via node — same NODE_EVAL pattern
as ssc.py, in case the legacy literal contains JS-only \\' escapes that are
invalid JSON but valid JS), asserts the count equals the legacy count, and
emits ONLY a JSON array of unified-schema question items to
/tmp/droid-bpsc-items.json (the coordinator merges these into data/bpsc.json;
this worker never writes data/*.json).

BPSC_DAILY_PROMPTS (prompt strings, NOT questions) is deliberately skipped.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (to be established at first successful run via node eval):
  BPSC_DAILY_MCQS = ~38 questions with "q" keys (legacy shape TBD from items)
"""
import json
import re
import subprocess
import sys
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/niteshlhsnda-droid/bpsc-pcs-prep/main/index.html"
EXPECTED_COUNT = 24  # node-eval-verified 2026-10-12 from complete 39,910-byte file (brief's 38 was a loose "q"-key grep estimate)

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
    # legacy BPSC_DAILY_MCQS shape: inspected at runtime; mapped to unified schema
    item = {
        "id": f"bpscd-{i + 1:06d}",   # bpscd- prefix: unique vs bpsc- (Wave 2B)
        "exams": ["bpsc"],
        "subject": str(x.get("subject", x.get("s", "")) or ""),
        "topic": str(x.get("topic", x.get("t", "")) or ""),
        "q": x.get("q", x.get("question", "")),
        "o": x.get("o", x.get("opts", x.get("options", []))),
        "a": x.get("a", x.get("answer", 0)),
        "e": str(x.get("e", x.get("why", x.get("explanation", ""))) or ""),
        "source": "niteshlhsnda-droid/bpsc-pcs-prep",
    }
    return item


def validate(item: dict, legacy_count: int) -> None:
    q, o, a = item["q"], item["o"], item["a"]
    assert isinstance(q, str) and q.strip(), f"empty q: {item['id']}"
    assert isinstance(o, list) and len(o) >= 2, f"o <2: {item['id']}"
    assert all(isinstance(x, str) and x.strip() for x in o), f"empty option: {item['id']}"
    assert isinstance(a, int) and 0 <= a < len(o), f"a out of range: {item['id']}"
    assert isinstance(item["subject"], str) and isinstance(item["topic"], str)
    assert isinstance(item["e"], str)
    assert re.fullmatch(r"[a-z]+-\d{6}", item["id"]), f"bad id: {item['id']}"


def main() -> int:
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/droid-bpsc.html")
    if not html_path.exists():
        # fetch the full raw file ourselves
        r = subprocess.run(
            ["curl", "-sL", "-o", str(html_path), LEGACY_URL],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            print(f"download failed: {r.stderr[:300]}")
            return 1
    html = html_path.read_text(errors="replace")
    print(f"legacy file: {html_path} ({len(html)} bytes)")
    if "BPSC_DAILY_MCQS" not in html:
        print("BPSC_DAILY_MCQS not found in legacy file — stopping, nothing written.")
        return 1

    mcqs = js_parse(html_path, "BPSC_DAILY_MCQS")

    # QA gate 1: exact count match with legacy (real parse path)
    status = "OK" if len(mcqs) == EXPECTED_COUNT else "MISMATCH"
    print(f"  legacy BPSC_DAILY_MCQS: {len(mcqs)} (expected {EXPECTED_COUNT}) [{status}]")
    if len(mcqs) != EXPECTED_COUNT:
        print("COUNT MISMATCH — stopping, not writing items file.")
        return 1
    assert all(x is not None for x in mcqs), "null hole in BPSC_DAILY_MCQS"

    # skip BPSC_DAILY_PROMPTS (prompts, not questions) — noted, never mapped
    if "BPSC_DAILY_PROMPTS" in html:
        print("  BPSC_DAILY_PROMPTS present — skipped (prompts are not questions).")

    items = [map_question(x, i) for i, x in enumerate(mcqs)]
    for it in items:
        validate(it, EXPECTED_COUNT)

    # no silent holes, unique well-formed ids
    ids = [it["id"] for it in items]
    assert len(set(ids)) == len(ids), "duplicate ids"

    out = Path("/tmp/droid-bpsc-items.json")
    out.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes) — {len(items)} items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
