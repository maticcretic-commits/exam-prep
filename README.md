# ExamPrep — one platform, every exam

A unified exam-preparation platform. One shared quiz engine, one stylesheet,
and pure-JSON question banks per exam — instead of N copied repos.

- **Live:** https://maticcretic-commits.github.io/exam-prep/
- **Per-exam app:** `exam/<slug>/` (e.g. `exam/ssc/`)

## Layout

```
index.html              # landing / exam picker (generated — do not edit by hand)
exam/<slug>/index.html  # per-exam app (generated — do not edit by hand)
assets/engine.js        # THE quiz engine — one copy, versioned
assets/style.css        # THE stylesheet — one copy
data/<slug>.json        # THE question bank per exam — pure data
data/meta.json          # exam registry (slugs, titles, colors, SEO)
tools/build.py          # static generator: data + templates -> HTML
tools/qa.py             # migration QA gate (counts, schema, render checks)
tools/extract/          # one extractor per legacy shape (throwaway after migration)
tools/templates/        # HTML templates used by build.py
```

## Refresh / add content

1. Update `data/<slug>.json` (questions, capsules, one-liners).
2. Run `python3 tools/build.py`.
3. Run `python3 tools/qa.py` — all gates must pass.
4. Push.

Never edit generated HTML by hand. Never regex-surgery a bank into a page.

## Adding a new exam

1. Write `tools/extract/<slug>.py` mapping the legacy bank to the unified schema.
2. Extract to `data/<slug>.json`.
3. Add the exam entry to `data/meta.json`.
4. Run build + QA. The exam page, landing card, filters and tabs appear automatically.
