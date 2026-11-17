"""eta.py   How long the full run has left, from the logs and the finished chunks.
  python3 scripts/step3_claims/eta.py"""
import glob, json, os, re, statistics, time
from datetime import datetime, timedelta

POOL = {"us": 268949, "ontario": 415686, "quebec": 348815}   # sentences per legislature (run_full_corpus.py --count)
CHUNK = 500
OUT = "outputs/full"
now = time.time()
speeds = {}
for j, n in POOL.items():
    total = -(-n // CHUNK)
    done = len(glob.glob(f"{OUT}/{j}/parses_[0-9]*.json"))
    log = f"{OUT}/log_{j}.txt"
    secs = []
    if os.path.exists(log):
        for line in open(log, encoding="utf-8", errors="replace"):
            m = re.search(r"chunk \d+: \d+ sentences, ([\d.]+)s each", line)
            if m:
                secs.append(float(m.group(1)))
    recent = secs[-12:]
    per = statistics.median(recent) if recent else None   # median of the last 12 chunks, so one slow chunk doesn't skew it
    if per:
        speeds[j] = per
    idle = (now - os.path.getmtime(log)) / 60 if os.path.exists(log) else None
    left = max(0, n - done * CHUNK)
    state = "not started" if not done else ("finished" if done >= total else ("running" if idle is not None and idle < 30 else f"no new chunk for {idle:.0f} min"))
    line = f"{j:8s} {done:4d}/{total} chunks  {state}"
    if per and done < total:
        hrs = left * per / 3600
        line += f"  {per:.2f}s a sentence  about {hrs:.1f} hours left (finishes about {(datetime.now() + timedelta(hours=hrs)):%a %H:%M} if it keeps running)"
    print(line)
if "us" not in speeds and "ontario" in speeds:
    print(f"us: at Ontario's speed, about {POOL['us'] * speeds['ontario'] / 3600:.1f} hours once started")
info = "outputs/student_pilot/run_info.json"
if os.path.exists(info):
    r = json.load(open(info))
    print(f"small model: {r['debate_sentences_per_second']} sentences a second, so all {sum(POOL.values()):,} sentences in about {sum(POOL.values()) / r['debate_sentences_per_second'] / 3600:.1f} hours")
