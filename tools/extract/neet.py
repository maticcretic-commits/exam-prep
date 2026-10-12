#!/usr/bin/env python3
"""Extractor for legacy neet-prep (maticcretic-commits/neet-prep).

Reads the FULL raw index.html, parses the two question banks with the page's
REAL parse paths, and emits data/neet.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy counts (established 2026-10-12 via node eval / real parse path):
  var extraQuestions = 164 items {s,m,q,o,a} (JS literal, node eval — the page
      renders each as a static article; the answer <details> shows
      item.a.slice(0,2) bolded = the answer letter, rest = explanation)
  <script type="application/json" id="emcq-data"> = 863 items
      {q, options, answer, explanation, topic?} — the page's real parse path is
      JSON.parse(document.getElementById('emcq-data').textContent)
  <script type="application/json" id="oneliner-data"> = 409 one-liners (strings)

Answer-key finding: extraQuestions' `a` is a STRING "A. <explanation>" whose
first char is the correct option letter; options are in A,B,C,D order (the
first 151 items carry "A. " prefixes, the numbered series 69-89 does not).
Verified spot-correct (e.g. pH of 0.001M NaOH -> "B. " -> index 1 -> "11").
Answer index = ord(a[0]) - ord('A'); explanation = a[2:] (may be empty).

Dedupe: 1 q-text appears in BOTH banks ("The 2026 Nobel Prize in Physiology or
Medicine was awarded for:") — the emcq version is kept, the extraQuestions
copy dropped. Extracted questions = 164 + 863 - 1 = 1026.

No <img> tags inside any question/option/answer text (checked 2026-10-12) —
the 21 <img> in the file are page chrome, no local asset refs to carry over.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

EXPECTED = {"extra": 164, "emcq": 863, "oneliners": 409}
DEDUPED = 1
TOTAL_Q = EXPECTED["extra"] + EXPECTED["emcq"] - DEDUPED

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const m = /(?:var|const|let)\s+extraQuestions\s*=\s*\[/.exec(html);
if (!m) { console.error('no decl: extraQuestions'); process.exit(1); }
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
if (depth !== 0) { console.error('unbalanced: extraQuestions'); process.exit(1); }
const arr = eval(html.slice(i, j + 1));  // real JS parse path, as the browser does
process.stdout.write(JSON.stringify(arr));
"""

NODE_JSONBLOCK = r"""
// the page's real parse path: JSON.parse(document.getElementById(id).textContent)
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const id = process.argv[2];
const m = new RegExp('<script[^>]*id="' + id + '"[^>]*>([\\s\\S]*?)</script>').exec(html);
if (!m) { console.error('no block: ' + id); process.exit(1); }
const arr = JSON.parse(m[1]);
process.stdout.write(JSON.stringify(arr));
"""


def node_eval(html_path: Path, script: str, arg: str = ""):
    args = ["node", "-e", script, str(html_path)]
    if arg:
        args.append(arg)
    r = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed ({arg or 'extraQuestions'}): {r.stderr[:500]}")
    return json.loads(r.stdout)


def check_item(x: dict):
    assert x["q"] and isinstance(x["q"], str), "empty q"
    assert isinstance(x["o"], list) and len(x["o"]) >= 2, "options < 2"
    assert all(isinstance(o, str) and o.strip() for o in x["o"]), "empty option"
    assert isinstance(x["a"], int) and 0 <= x["a"] < len(x["o"]), "answer out of range"
    for k in ("subject", "topic", "module", "e"):
        assert isinstance(x[k], str), f"{k} not str"
    assert "<img" not in (x["q"] + " ".join(x["o"]) + x["e"]).lower(), "<img> in item"


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w2b-neet-prep.html")
    html = html_path.read_text(errors="replace")
    print(f"legacy file: {html_path} ({len(html)} bytes)")

    extra = node_eval(html_path, NODE_EVAL)
    emcq = node_eval(html_path, NODE_JSONBLOCK, "emcq-data")
    onel = node_eval(html_path, NODE_JSONBLOCK, "oneliner-data")

    for label, got, want in [("extraQuestions", len(extra), EXPECTED["extra"]),
                             ("emcq-data", len(emcq), EXPECTED["emcq"]),
                             ("oneliner-data", len(onel), EXPECTED["oneliners"])]:
        status = "OK" if got == want else "MISMATCH"
        print(f"  legacy {label}: {got} (expected {want}) [{status}]")
        if got != want:
            print("COUNT MISMATCH — stopping, not writing data file.")
            return 1
    assert all(x is not None for x in extra + emcq), "null hole in banks"
    assert all(isinstance(t, str) and t.strip() for t in onel), "bad oneliner"

    # sanity on emcq answer keys (ints in range) — the real parse path gives these
    bad = [x for x in emcq
           if not isinstance(x.get("answer"), int)
           or not (0 <= x["answer"] < len(x.get("options", [])))]
    assert not bad, f"{len(bad)} emcq items with bad answer key"

    emcq_qs = {x["q"] for x in emcq}
    questions = []
    skipped = 0
    for x in extra:
        if x["q"] in emcq_qs:  # dedupe: keep the emcq version
            skipped += 1
            continue
        a = x.get("a", "")
        m = re.fullmatch(r"([A-D])\.\s?(.*)", a, re.DOTALL)
        assert m, f"answer not 'L. ...' shaped: {a[:60]!r}"
        idx = ord(m.group(1)) - 65
        assert idx < len(x["o"]), "answer letter beyond options"
        questions.append({
            "id": "",  # filled below
            "exams": ["neet"],
            "subject": (x.get("s") or "").strip().title(),
            "module": (x.get("m") or "").strip(),
            "topic": "",
            "difficulty": "",
            "q": x["q"],
            "o": x["o"],
            "a": idx,
            "e": m.group(2).strip(),
            "source": "neet-prep",
        })
    print(f"  extraQuestions deduped: skipped {skipped} (expected {DEDUPED})")
    assert skipped == DEDUPED, "dedupe count changed — re-examine"

    for x in emcq:
        t = (x.get("topic") or "").strip()
        if "\u203a" in t:
            subject, topic = [p.strip() for p in t.split("\u203a", 1)]
        elif t:
            subject, topic = t, ""
        else:
            subject, topic = "", ""
        questions.append({
            "id": "",
            "exams": ["neet"],
            "subject": subject,
            "module": "",
            "topic": topic,
            "difficulty": "",
            "q": x["q"],
            "o": x["options"],
            "a": x["answer"],
            "e": x.get("explanation", ""),
            "source": "neet-prep",
        })

    assert len(questions) == TOTAL_Q, f"extracted {len(questions)} != legacy {TOTAL_Q}"
    for n, x in enumerate(questions):
        x["id"] = f"neet-{n + 1:06d}"
        check_item(x)
    ids = [x["id"] for x in questions]
    assert len(set(ids)) == len(ids), "duplicate ids"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", i) for i in ids), "bad id shape"

    oneliners = [
        {"id": f"neet-ol-{i + 1:06d}", "subject": "", "text": t}
        for i, t in enumerate(onel)
    ]

    data = {
        "exam": "neet",
        "title": "NEET Preparation",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": [],
        "oneliners": oneliners,
        "videos": [],
        "listings": [],
    }
    blob = json.dumps(data, ensure_ascii=False)
    assert not re.search(r"\bMuse\b", blob), "'Muse' mention in content"
    out = root / "data" / "neet.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  questions={len(questions)} oneliners={len(oneliners)}")
    print("SELF-CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
