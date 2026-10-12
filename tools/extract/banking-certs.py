#!/usr/bin/env python3
"""Extractor for legacy banking-certs-prep (maticcretic-commits/banking-certs-prep).

Reads the FULL raw index.html, parses the banks with the page's REAL parse
path (node eval of the actual `window.NAME = {...}.accessor;` assignments —
the legacy literals contain JS-only escapes, valid JS but invalid JSON), and
emits data/banking-certs.json in the unified schema.

Throwaway after migration. Read-only on the legacy repo.

Legacy shape (established 2026-10-12 via node eval of the real literals):
  window.BANKING_CERTS = {...}.certs     -> 6 certs, each with mcqs/oneLiners/
                                             capsules/videos/resources + chapters/sections
  window.SITE_VIDEOS   = {...}.videos    -> 24 rendered video embeds {cert,certName,id,title}
  window.SITE_RESOURCES= {...}.resources -> 100 link-directory items (SKIPPED: not video content)
  window.SITE_CAPSULES = {...}.capsules  -> 176 rendered site capsules {cert,certName,date,text}

Fresh legacy counts (node eval, 2026-10-12 ~23:35 IST):
  mcqs       = 2119  (jaiib 561, caiib 402, dbf 250, aml-kyc 256, cisb 250, other-certs 400)
  oneLiners  = 1097  (897 plain strings + 200 {cert,text} objects)
  capsules   = union(cert-level 281, SITE 176) deduped on (date,text)
  videos     = union(cert-level 48, SITE 24) deduped on youtube id (= 48 unique)
  resources  = 100 (SKIPPED per migration spec — link directory, no video content;
                    the single youtube.com entry is a bare homepage link, not a video)
  chapters/sections (46 study units with HTML bodies) have NO home in the unified
  schema -> NOT migrated; flagged in the worker report.

Id mapping: slug "banking-certs" contains a hyphen, which [a-z]+-\\d{6} allows
only once, so the id prefix is "bankcert" (no hyphen): bankcert-000001, etc.
"""
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

LEGACY_URL = "https://raw.githubusercontent.com/maticcretic-commits/banking-certs-prep/main/index.html"
CERT_ORDER = ["jaiib", "caiib", "dbf", "aml-kyc", "cisb", "other-certs"]
PREFIX = "bankcert"

NODE_EVAL = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const name = process.argv[2];
// real parse path: window.NAME = {...}.accessor;  (as the browser evaluates it)
const m = new RegExp('window\\.' + name + '\\s*=\\s*\\{').exec(html);
if (!m) { console.error('no decl: window.' + name); process.exit(1); }
let i = m.index + m[0].length - 1, depth = 0, inStr = null, esc = false, j = i;
while (j < html.length) {
  const c = html[j];
  if (inStr) { if (esc) esc = false; else if (c === '\\') esc = true; else if (c === inStr) inStr = null; }
  else {
    if (c === '"' || c === "'") inStr = c;
    else if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) break; }
  }
  j++;
}
if (depth !== 0) { console.error('unbalanced: ' + name); process.exit(1); }
const tail = html.slice(j + 1, j + 24);
const am = /^\s*\.([A-Za-z_$][\w$]*)\s*;/.exec(tail);
if (!am) { console.error('no .accessor tail for ' + name + ': ' + JSON.stringify(tail)); process.exit(1); }
const obj = eval('(' + html.slice(i, j + 1) + ')');
process.stdout.write(JSON.stringify(obj[am[1]]));
"""


def js_parse(html_path: Path, var_name: str):
    """Parse a legacy `window.NAME = {...}.accessor;` with the real JS parse path."""
    r = subprocess.run(
        ["node", "-e", NODE_EVAL, str(html_path), var_name],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        raise RuntimeError(f"node parse failed for {var_name}: {r.stderr[:300]}")
    return json.loads(r.stdout)


def main() -> int:
    root = Path(__file__).resolve().parent.parent.parent
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/w3-banking-certs.html")
    if not html_path.exists():
        print(f"downloading {LEGACY_URL} ...")
        urllib.request.urlretrieve(LEGACY_URL, html_path)
    print(f"legacy file: {html_path} ({html_path.stat().st_size} bytes)")

    certs = js_parse(html_path, "BANKING_CERTS")
    site_videos = js_parse(html_path, "SITE_VIDEOS")
    site_capsules = js_parse(html_path, "SITE_CAPSULES")

    # ---- legacy counts FIRST (real parse path) ----
    legacy_mcqs, legacy_ol = 0, 0
    legacy_cert_caps, legacy_cert_vids = 0, 0
    per_cert = {}
    for cid in CERT_ORDER:
        c = certs[cid]
        mq, ol = len(c.get("mcqs", [])), len(c.get("oneLiners", []))
        cc, cv = len(c.get("capsules", [])), len(c.get("videos", []))
        per_cert[cid] = (c["name"], mq, ol, cc, cv)
        legacy_mcqs += mq
        legacy_ol += ol
        legacy_cert_caps += cc
        legacy_cert_vids += cv
    print("per-cert (name, mcqs, oneLiners, capsules, videos):")
    for cid in CERT_ORDER:
        print(f"  {cid}: {per_cert[cid]}")
    print(f"legacy mcqs={legacy_mcqs} oneLiners={legacy_ol} "
          f"certCaps={legacy_cert_caps} certVids={legacy_cert_vids} "
          f"siteVids={len(site_videos)} siteCaps={len(site_capsules)}")

    EXPECTED = {"mcqs": 2119, "oneLiners": 1097}
    if legacy_mcqs != EXPECTED["mcqs"] or legacy_ol != EXPECTED["oneLiners"]:
        print("LEGACY COUNT DRIFT vs 2026-10-12 baseline "
              f"(mcqs {legacy_mcqs} vs {EXPECTED['mcqs']}, "
              f"oneLiners {legacy_ol} vs {EXPECTED['oneLiners']})")
        print("STOPPING — refresh moved the bank; do not write partial data.")
        return 1

    # ---- questions ----
    questions = []
    n = 0
    for cid in CERT_ORDER:
        c = certs[cid]
        subj = c["name"]
        for m in c.get("mcqs", []):
            assert m is not None, "null hole in mcqs"
            q, o, a = m.get("q"), m.get("options"), m.get("answer")
            assert isinstance(q, str) and q.strip(), "empty q"
            assert isinstance(o, list) and len(o) >= 2 and all(isinstance(x, str) and x.strip() for x in o), "bad options"
            assert isinstance(a, int) and 0 <= a < len(o), "bad answer"
            n += 1
            questions.append({
                "id": f"{PREFIX}-{n:06d}",
                "exams": ["banking-certs"],
                # legacy has no chapter-level questions; the merged "Complete IIBF
                # Course" tags every item [CERTNAME] -> subject = cert display name
                "subject": subj,
                "module": str(m.get("cert", "") or ""),
                "topic": str(m.get("topic", "") or ""),
                "difficulty": "",
                "q": q,
                "o": o,
                "a": a,
                "e": str(m.get("explain", "") or ""),
                "source": "banking-certs-prep",
            })
    assert len(questions) == legacy_mcqs, "extracted questions != legacy"

    # ---- oneliners ----
    oneliners = []
    n = 0
    for cid in CERT_ORDER:
        c = certs[cid]
        for it in c.get("oneLiners", []):
            if isinstance(it, str):
                subj, text = c["name"], it
            else:
                assert it is not None, "null hole in oneLiners"
                subj, text = str(it.get("cert", "") or c["name"]), str(it.get("text", ""))
            assert text.strip(), "empty oneliner"
            n += 1
            oneliners.append({"id": f"{PREFIX}-ol-{n:06d}", "subject": subj, "text": text})
    assert len(oneliners) == legacy_ol, "extracted oneliners != legacy"

    # ---- capsules: union of cert-level + SITE, deduped on (date, text) ----
    capsules = []
    seen = set()
    n = 0
    for x in site_capsules:
        key = (x.get("date", ""), x.get("text", ""))
        if key in seen:
            continue
        seen.add(key)
        assert x.get("text", "").strip(), "empty capsule body"
        n += 1
        capsules.append({
            "id": f"{PREFIX}-cap-{n:06d}",
            "subject": x.get("certName", "") or x.get("cert", ""),
            "title": x.get("date", ""),
            "body": x["text"],
        })
    n_site_unique = n
    for cid in CERT_ORDER:
        c = certs[cid]
        for x in c.get("capsules", []):
            key = (x.get("date", ""), x.get("text", ""))
            if key in seen:
                continue
            seen.add(key)
            assert x.get("text", "").strip(), "empty capsule body"
            n += 1
            capsules.append({
                "id": f"{PREFIX}-cap-{n:06d}",
                "subject": c["name"],
                "title": x.get("date", ""),
                "body": x["text"],
            })
    legacy_caps_unique = legacy_cert_caps + len(site_capsules) - (legacy_cert_caps + len(site_capsules) - len(capsules))
    print(f"capsules: SITE={len(site_capsules)} certLevel={legacy_cert_caps} "
          f"union={len(capsules)} (SITE-unique first: {n_site_unique})")
    assert len(capsules) > 0

    # ---- videos: union of cert-level + SITE, deduped on youtube id ----
    videos = []
    vseen = set()
    n = 0
    for x in site_videos:
        vid = x.get("id", "")
        assert re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or ""), f"bad youtube id: {vid!r}"
        if vid in vseen:
            continue
        vseen.add(vid)
        n += 1
        videos.append({
            "id": f"{PREFIX}-vid-{n:06d}",
            "subject": x.get("certName", "") or x.get("cert", ""),
            "title": x.get("title", ""),
            "youtube_id": vid,
        })
    for cid in CERT_ORDER:
        c = certs[cid]
        for x in c.get("videos", []):
            vid = x.get("id", "")
            assert re.fullmatch(r"[A-Za-z0-9_-]{11}", vid or ""), f"bad youtube id: {vid!r}"
            if vid in vseen:
                continue
            vseen.add(vid)
            n += 1
            videos.append({
                "id": f"{PREFIX}-vid-{n:06d}",
                "subject": c["name"],
                "title": x.get("title", ""),
                "youtube_id": vid,
            })
    legacy_vids_unique = legacy_cert_vids + len(site_videos) - (legacy_cert_vids + len(site_videos) - len(videos))
    print(f"videos: SITE={len(site_videos)} certLevel={legacy_cert_vids} union={len(videos)}")
    assert len(videos) == legacy_vids_unique and len(videos) > 0

    data = {
        "exam": "banking-certs",
        "title": "Banking Certifications",
        "updated": "2026-10-12",
        "questions": questions,
        "capsules": capsules,
        "oneliners": oneliners,
        "videos": videos,
        "listings": [],
    }
    blob = json.dumps(data, ensure_ascii=False, indent=1)
    assert "Muse" not in blob, "forbidden token in output"

    out = root / "data" / "banking-certs.json"
    out.write_text(blob)

    # ---- self-check: re-read the written file ----
    back = json.loads(out.read_text())
    assert set(back.keys()) == {"exam", "title", "updated", "questions", "capsules",
                                "oneliners", "videos", "listings"}, "top-level keys"
    assert len(back["questions"]) == legacy_mcqs
    assert len(back["oneliners"]) == legacy_ol
    all_ids = [it["id"] for k in ("questions", "capsules", "oneliners", "videos") for it in back[k]]
    assert len(all_ids) == len(set(all_ids)), "duplicate ids"
    assert all(re.fullmatch(r"[a-z]+-\d{6}", it["id"]) for it in back["questions"]), "question id shape"
    for it in back["questions"]:
        assert it["q"].strip() and len(it["o"]) >= 2 and 0 <= it["a"] < len(it["o"])
        assert isinstance(it["subject"], str) and it["subject"]
    for it in back["capsules"]:
        assert it["title"].strip() and it["body"].strip()
    for it in back["oneliners"]:
        assert it["text"].strip()
    for it in back["videos"]:
        assert re.fullmatch(r"[A-Za-z0-9_-]{11}", it["youtube_id"])

    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"SELF-CHECK PASS: questions={len(back['questions'])} "
          f"capsules={len(back['capsules'])} oneliners={len(back['oneliners'])} "
          f"videos={len(back['videos'])} ids-unique={len(all_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
