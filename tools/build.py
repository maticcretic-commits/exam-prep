#!/usr/bin/env python3
"""ExamPrep static generator.

Reads data/meta.json (exam registry) + data/<slug>.json (unified banks),
renders tools/templates/*.html, and emits:
  index.html               — landing / exam picker
  exam/<slug>/index.html   — per-exam app shell (data loaded at runtime via fetch)

Refresh flow: update data/*.json -> run this -> push. No HTML surgery, ever.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = Path(__file__).resolve().parent


def render(tpl: str, ctx: dict) -> str:
    for k, v in ctx.items():
        tpl = tpl.replace("{{" + k + "}}", str(v))
    assert "{{" not in tpl, f"unrendered placeholder remains: {tpl[tpl.index('{{')-20:tpl.index('{{')+30]}"
    return tpl


def main() -> int:
    meta = json.loads((ROOT / "data" / "meta.json").read_text())
    exams = meta["exams"]
    engine_v = meta.get("engine_version", "1.0.0")
    landing_tpl = (TOOLS / "templates" / "landing.html").read_text()
    exam_tpl = (TOOLS / "templates" / "exam.html").read_text()

    cards = []
    for ex in exams:
        slug = ex["slug"]
        bank = json.loads((ROOT / "data" / f"{slug}.json").read_text())
        qn, oln, capn = len(bank["questions"]), len(bank["oneliners"]), len(bank["capsules"])
        vidn, listn = len(bank.get("videos", [])), len(bank.get("listings", []))
        resn = len(bank.get("resources", []))

        # per-exam page
        page = render(exam_tpl, {
            "TITLE": ex["title"],
            "SLUG": slug,
            "DESCRIPTION": ex.get("description", ex["title"]),
            "QCOUNT": qn,
            "OLCOUNT": oln,
            "CAPCOUNT": capn,
            "VIDCOUNT": vidn,
            "LISTCOUNT": listn,
            "RESCOUNT": resn,
            "ENGINE_VERSION": engine_v,
        })
        out = ROOT / "exam" / slug / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page)
        print(f"  exam/{slug}/index.html  (q={qn} ol={oln} cap={capn} vid={vidn} list={listn} res={resn})")

        parts = []
        if qn: parts.append(f"{qn} MCQs")
        if oln: parts.append(f"{oln} one-liners")
        if capn: parts.append(f"{capn} capsules")
        if listn: parts.append(f"{listn} vacancies")
        if vidn: parts.append(f"{vidn} videos")
        if resn: parts.append(f"{resn} resources")
        cards.append(
            f'    <a class="examcard" style="border-top-color:{ex.get("color", "#1a73e8")}" href="exam/{slug}/">\n'
            f'      <h2>{ex.get("short", ex["title"])}</h2>\n'
            f'      <p>{" · ".join(parts) or "Content coming soon"}</p>\n'
            f'    </a>\n'
        )

    landing = render(landing_tpl, {
        "TAGLINE": meta.get("tagline", ""),
        "UPDATED": meta.get("updated", ""),
        "ENGINE_VERSION": engine_v,
        "EXAM_CARDS": "".join(cards),
    })
    (ROOT / "index.html").write_text(landing)
    print(f"  index.html ({len(exams)} exam cards)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
