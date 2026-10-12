#!/usr/bin/env python3
"""ExamPrep single refresh pipeline — replaces the 21 legacy per-repo refresh crons.

The cron worker researches fresh content, writes it to a JSON file, and runs:
    python3 tools/refresh.py --items /tmp/refresh-items-<date>-<slot>.json --slot morning|evening

Input format:
    {"<slug>": {"questions": [...], "oneliners": [...], "capsules": [...], "listings": [...]}, ...}
Question items need: subject, q, o (options), a (answer idx), e (explanation);
topic/module/difficulty/qual etc. optional. IDs are assigned automatically.

What this script does per slug:
  1. Dedupe by id (skip items whose id already exists).
  2. Duplicate screen on questions (legacy rule): lowercase -> numbers to "#"
     -> strip punctuation -> 8-word shingles -> Jaccard >= 0.80 vs the whole
     existing bank. Dupes are dropped, never added.
  3. Assign ids continuing the exam's sequence ({prefix}-{NNNNNN}).
  4. Append, stamp "updated", and record counts.
Then:
  5. Raise qa.py EXPECTED baselines for changed slugs (never lower them).
  6. Run build.py + qa.py — any QA failure aborts before push.
  7. Push changed data files + qa.py + rebuilt pages via gh-api put-file.
  8. SHA-verify each push; append per-exam lines to the progress log.

Strictly additive: never modifies or deletes existing items (mirrors the
legacy crons' FORBIDDEN list). Closed listings are never deleted — the
engine's deadline sort sinks them below open ones with "Closed" badges.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GH = Path.home() / "workspace" / "skills" / "github" / "bin" / "gh-api"
LOGDIR = Path.home() / "workspace" / "goals" / "exam-prep-hub-websites" / "hidden_files"

ID_RE = re.compile(r"^([a-z]+)-(\d+)$")


def norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\d+", "#", t)
    t = re.sub(r"[^a-z#\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def shingles(text: str, n: int = 8) -> set:
    w = norm(text).split()
    if len(w) < n:
        return {" ".join(w)} if w else set()
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def qtext(q: dict) -> str:
    return (q.get("q") or "") + " " + " ".join(q.get("o") or [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True, help="JSON file with new items per slug")
    ap.add_argument("--slot", required=True, choices=["morning", "evening"])
    ap.add_argument("--dry-run", action="store_true", help="validate + report, do not push")
    args = ap.parse_args()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items = json.loads(Path(args.items).read_text())
    log_path = LOGDIR / f"refresh-{today}-{args.slot}.log"

    changed = {}   # slug -> {added counts}
    failures = []

    for slug, bundle in items.items():
        bank_path = ROOT / "data" / f"{slug}.json"
        if not bank_path.exists():
            failures.append(f"{slug}: unknown exam slug")
            continue
        bank = json.loads(bank_path.read_text())
        existing_ids = {q["id"] for q in bank["questions"]}
        existing_ids |= {o["id"] for o in bank["oneliners"]}
        existing_ids |= {c["id"] for c in bank["capsules"]}
        existing_ids |= {v["id"] for v in bank["videos"]}
        existing_ids |= {l["id"] for l in bank["listings"]}

        # id sequence state for questions
        prefix, maxseq = None, 0
        for q in bank["questions"]:
            m = ID_RE.fullmatch(q.get("id") or "")
            if m:
                prefix = prefix or m.group(1)
                maxseq = max(maxseq, int(m.group(2)))

        # duplicate screen corpus: shingles of every existing question
        corpus = [(q["id"], shingles(qtext(q))) for q in bank["questions"]]

        added = {"questions": 0, "oneliners": 0, "capsules": 0, "listings": 0}
        slug_src = f"{slug}-prep"

        for q in bundle.get("questions", []):
            if q.get("id") and q["id"] in existing_ids:
                continue
            o, a = q.get("o"), q.get("a")
            if not isinstance(o, list) or len(o) < 2 or not isinstance(a, int) or not (0 <= a < len(o)):
                failures.append(f"{slug}: dropped question with bad options/answer: {(q.get('q') or '')[:60]}")
                continue
            if not (q.get("subject") or "").strip() or not (q.get("q") or "").strip():
                failures.append(f"{slug}: dropped question missing subject/text")
                continue
            sq = shingles(qtext(q))
            if any(jaccard(sq, es) >= 0.80 for _, es in corpus):
                continue  # duplicate of existing bank item
            maxseq += 1
            qid = f"{prefix}-{maxseq:06d}"
            if qid in existing_ids:
                failures.append(f"{slug}: id collision {qid} — aborting slug")
                break
            bank["questions"].append({
                "id": qid,
                "exams": [slug],
                "subject": q["subject"],
                "module": q.get("module", ""),
                "topic": q.get("topic", ""),
                "difficulty": q.get("difficulty", "medium"),
                "q": q["q"], "o": o, "a": a, "e": q.get("e", ""),
                "source": slug_src,
            })
            existing_ids.add(qid)
            corpus.append((qid, sq))
            added["questions"] += 1

        for kind, key in (("oneliners", "text"), ("capsules", "title")):
            for it in bundle.get(kind, []):
                if it.get("id") and it["id"] in existing_ids:
                    continue
                if not (it.get(key) or "").strip():
                    continue
                maxseq += 1
                iid = f"{prefix}-{maxseq:06d}"
                entry = {"id": iid, "subject": it.get("subject", "")}
                if kind == "oneliners":
                    entry["text"] = it["text"]
                else:
                    entry["title"] = it["title"]
                    entry["body"] = it.get("body", "")
                bank["oneliners" if kind == "oneliners" else "capsules"].append(entry)
                existing_ids.add(iid)
                added[kind] += 1

        for l in bundle.get("listings", []):
            lid = l.get("id") or re.sub(r"[^a-z0-9]+", "-", (l.get("title") or "").lower()).strip("-")
            if not lid or lid in existing_ids:
                continue
            if not (l.get("title") or "").strip() or not (l.get("org") or "").strip():
                failures.append(f"{slug}: dropped listing missing title/org")
                continue
            l["id"] = lid
            if not l.get("verifyNote"):
                l["verifyNote"] = f"Verified: {today}"
            bank["listings"].append(l)
            existing_ids.add(lid)
            added["listings"] += 1

        if any(added.values()):
            bank["updated"] = today
            bank_path.write_text(json.dumps(bank, ensure_ascii=False))
            changed[slug] = added
            print(f"  {slug}: +{added['questions']}q +{added['oneliners']}ol +{added['capsules']}cap +{added['listings']}list")

    if failures:
        print("refresh ABORTED — input problems:")
        for f in failures:
            print("  FAIL:", f)
        return 1
    if not changed:
        print("refresh: nothing new to add (all dupes/skipped).")
        return 0

    # raise qa.py EXPECTED baselines (only upward) so the gate keeps guarding
    qa_path = ROOT / "tools" / "qa.py"
    qa_src = qa_path.read_text()
    m = re.search(r"EXPECTED = (\{.*?\n\})", qa_src, re.S)
    if not m:
        print("refresh ABORTED: cannot find EXPECTED block in qa.py")
        return 1
    expected = eval(m.group(1))
    for slug, added in changed.items():
        bank = json.loads((ROOT / "data" / f"{slug}.json").read_text())
        for k in ("questions", "oneliners", "capsules", "videos", "listings", "resources"):
            new_n = len(bank.get(k, []))
            old_n = expected.get(slug, {}).get(k, 0)
            if new_n < old_n:
                print(f"refresh ABORTED: {slug}.{k} would drop {old_n} -> {new_n}")
                return 1
            if new_n != old_n:
                expected.setdefault(slug, {})[k] = new_n
    new_block = "EXPECTED = " + json.dumps(expected, indent=4).replace('"', '"')
    # keep python-dict style: json.dumps output is valid python for this shape
    qa_src = qa_src[:m.start(1)] + new_block + qa_src[m.end(1):]
    qa_path.write_text(qa_src)
    print("  qa.py EXPECTED baselines raised")

    # rebuild + gate
    print("running build.py...")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "build.py")], capture_output=True, text=True)
    if r.returncode != 0:
        print("build.py FAILED:\n", r.stderr[-2000:])
        return 1
    print("running qa.py...")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "qa.py")], capture_output=True, text=True)
    print(r.stdout[-1500:])
    if r.returncode != 0 or "QA GATE: ALL PASS" not in r.stdout:
        print("refresh ABORTED: QA gate did not pass — nothing pushed.")
        return 1

    if args.dry_run:
        print("dry-run: validated, not pushing.")
        return 0

    # push: changed data files + qa.py + rebuilt pages
    push_files = [f"data/{s}.json" for s in changed] + ["tools/qa.py", "index.html"] + \
                 [f"exam/{s}/index.html" for s in changed]
    msg = f"Refresh {today} {args.slot}: " + ", ".join(
        f"{s} +{a['questions']}q+{a['oneliners']}ol+{a['capsules']}cap+{a['listings']}l" for s, a in changed.items())
    ok_slugs = []
    for f in push_files:
        r = subprocess.run([str(GH), "put-file", "maticcretic-commits/exam-prep", f,
                            "--message", msg, "--content", "-"],
                           stdin=open(ROOT / f, "rb"), capture_output=True)
        if r.returncode != 0:
            print(f"  PUSH FAIL {f}: {r.stderr.decode()[:200]}")
            failures.append(f)
        else:
            print(f"  pushed {f}")
    # SHA-verify via git trees
    if not failures:
        import urllib.request
        sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
        from dynamic_credentials import add_surrogate_to_request, read_json_response
        req = urllib.request.Request(
            "https://api.github.com/repos/maticcretic-commits/exam-prep/git/trees/main?recursive=1")
        add_surrogate_to_request(req, "custom.github", allowed_hosts=["api.github.com"])
        tree = read_json_response(urllib.request.urlopen(req, timeout=30))
        blobs = {t["path"]: t["sha"] for t in tree["tree"] if t["type"] == "blob"}
        for f in push_files:
            local = subprocess.run(["git", "hash-object", str(ROOT / f)],
                                   capture_output=True, text=True).stdout.strip()
            status = "SHA-ok" if blobs.get(f) == local else "SHA-MISMATCH"
            print(f"  {status} {f}")
            if blobs.get(f) != local:
                failures.append(f + " sha-mismatch")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path, "a") as log:
        for s in changed:
            log.write(f"{s} {'OK' if s not in failures else 'FAIL'} {ts}\n")
    if failures:
        print("refresh finished WITH FAILURES:", failures)
        return 1
    print(f"refresh {args.slot} complete: {len(changed)} exams updated, log {log_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
