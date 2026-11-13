_DEBATE_REAL = re.compile(r"DEBATE\s*-|Considered under suspension|Considered under the provisions of rule|"
                          r"Committee of the Whole|GENERAL DEBATE|moved to suspend the rules|moved that the House suspend|"
                          r"Called up by|Considered as privileged|proceeded with|Considered as unfinished business", re.I)
_RULE_ACT = re.compile(r"(?:Rule|Rules Committee Resolution)\s+H\.\s?Res\.\s?(\d+)", re.I)


def _section_inputs(plan):
    """Per bill from its Congress.gov action list: days of any House floor action, days of House floor
    DEBATE (not passage by unanimous consent alone), the H. Res. rules listed for it, and its titles;
    plus the by-hand checks (data/us/v3/section_hand_checks.json)."""
    status = rp("data", "v3_status_cache", "us")
    try:
        from compare_debate_days import house_floor
    except Exception:                                   # noqa: BLE001
        house_floor = None
    floor, debate, rules, titles = {}, {}, {}, {}
    for bk in sorted({b["bill_key"] for b in plan}):
        acts = (load_json(os.path.join(status, f"{bk}.actions.json")) or {}).get("actions")
        if acts is not None and house_floor is not None:
            floor[bk] = set(house_floor(acts))
            debate[bk] = set()
            rules[bk] = set()
            for a in acts:
                t = str(a.get("text", ""))
                d = str(a.get("actionDate", ""))[:10]
                src = str((a.get("sourceSystem") or {}).get("name", ""))
                rules[bk] |= {int(x) for x in _RULE_ACT.findall(t)}
                if not d or "Senate" in src or (re.search(r"\bSenate\b", t) and not re.search(r"\bHouse\b", t)):
                    continue
                if _DEBATE_REAL.search(t) and not re.match(r"^\s*(Rules\s*Committee|Committee on Rules|Rule\s+H)", t, re.I):
                    debate[bk].add(d)
        bill = (load_json(os.path.join(status, f"{bk}.bill.json")) or {}).get("bill") or {}
        titles[bk] = [t for t in (bill.get("title"), (bill.get("latestTitle") or "")) if t]
    hand = load_json(os.path.join(OUT, "section_hand_checks.json"), {}) or {}
    own = hand.get("own_debate_titles", {})
    vehicle = {(v[0], v[1]) for v in hand.get("vehicle_days", [])}
    joint = defaultdict(list)                          # bill_key -> [(day, item title)] read by hand as a joint debate
    for j in hand.get("joint_debates", []):
        joint[j[0]].append((j[1], j[2]))
    return floor, debate, rules, titles, own, vehicle, joint


_TAG_RANK = {"debate": 3, "vehicle": 3, "companion": 3, "speech": 2, "rule": 2, "held": 1}


def cmd_segment():
    # PATCHED_SECTIONS_2026_10_02 PATCHED_SECTIONS2_2026_10_02 PATCHED_SECTIONS3_2026_10_02 PATCHED_SECTIONS4_2026_10_03 PATCHED_SECTIONS5_2026_10_03: text belongs to a bill only from the Record's own line that brings
    # that bill before the House (us_sections.py); other measures' debates and procedural items are
    # taken out only when two independent checks agree; speeches, printed text, roll-call lists and
    # vehicle days are tagged paragraph by paragraph (para_tags) so the choices file decides later.
    import us_sections as SEC
    plan = load_json(PLAN) or sys.exit("Run plan first.")
    os.makedirs(SEG_DIR, exist_ok=True)
    index, missing, emptied = [], [], []
    merged = {}                # (bill_key, debate_day) -> one entry, whichever votes reach it
    extra = floor_extra(plan) if os.path.exists(FLOOR) else {}
    floor, debate, rules, titles, own, vehicle, joint = _section_inputs(plan)
    plan_keys = {(str(b["congress"]), str(b["type"]).lower(), int(b["number"])) for b in plan}
    # round 5: the days the segment step reads for each bill (its vote windows and Congress.gov debate days), so a
    # piece another bill keeps on its own bill-day that day is not held here as well
    plan_days = defaultdict(set)
    for j, b in enumerate(plan):
        plan_days[(str(b["congress"]), str(b["type"]).lower(), int(b["number"]))] |= set(window_days(b)) | set(extra.get(j, set()))
    if extra:
        print(f"also searching {sum(len(v) for v in extra.values())} Congress.gov House debate days "
              f"outside the vote windows (floor_days.json)", flush=True)
    for i, b in enumerate(plan, 1):
        hint = set()               # old text files are not used any more
        units_by_day = {}
        for day in window_days(b):
            units_by_day[day] = daily_units(day) if b["edition"] == "daily" else bound_units(day, hint)
        floor_days = sorted(extra.get(i - 1, set()))
        for day in floor_days:
            units_by_day[day] = daily_units(day) if day >= DAILY_FROM else bound_units(day, hint)
        d0 = dt.date.fromisoformat(b["vote_date"])
        chosen, excluded = select_units(units_by_day, b)
        rx = us_bill_mention_re(b["type"], b["number"])
        res = SEC.refine(b, units_by_day, chosen or [], rx, is_proc_title, frozenset(GENERIC_TITLES),
                         titles.get(b["bill_key"], []), floor.get(b["bill_key"]), own.get(b["bill_key"], []), vehicle,
                         debate_days=debate.get(b["bill_key"]), plan_keys=plan_keys,
                         rules_of_bill=frozenset(rules.get(b["bill_key"], set())), joint=tuple(joint.get(b["bill_key"], ())),
                         plan_days=plan_days)
        kept_days = {d for d, r in res.items() if r["paras"]}
        if not kept_days and not chosen:
            missing.append({**b, "days_searched": list(units_by_day),
                            "units_available": {d: len(u) for d, u in units_by_day.items()}, "excluded": excluded})
            print(f"  [{i}/{len(plan)}] {b['bill_key']} {b['vote_date']}: NOT FOUND", flush=True)
            continue
        for day, r in sorted(res.items()):
            k = (d0 - dt.date.fromisoformat(day)).days
            src = ("congress_gov_floor_day" if day in floor_days else
                   "vote_date" if k == 0 else f"vote_date_minus_{k}")
            m = merged.get((b["bill_key"], day))
            if m is None or (src != "congress_gov_floor_day" and (m["src"] == "congress_gov_floor_day" or k < m["k"])):
                prev = m
                m = {"b": b, "k": k, "src": src, "floor": day in floor_days,
                     "paras": prev["paras"] if prev else {}, "units": prev["units"] if prev else {},
                     "removed": prev["removed"] if prev else {}, "held": prev["held"] if prev else {},
                     "notes": prev["notes"] if prev else {},
                     "added": prev["added"] if prev else 0, "votes": prev["votes"] if prev else [],
                     "excluded": prev["excluded"] if prev else []}
                merged[(b["bill_key"], day)] = m
            for order, uid, idx, text, tag in r["paras"]:
                old = m["paras"].get((order, uid, idx))
                if old is None or _TAG_RANK[tag.split("+")[0]] > _TAG_RANK[old[1].split("+")[0]]:
                    m["paras"][(order, uid, idx)] = (text, tag)
            for u, meth in (chosen or []):
                if u["day"] == day:
                    m["units"].setdefault(u["id"], {"id": u["id"], "title": u["title"], "method": meth,
                                                    "source": u["source"], "printed": u.get("printed", {}),
                                                    "url": u.get("url", "")})
            for u in units_by_day.get(day, []):
                if u["id"] in r["units"] and u["id"] not in m["units"]:
                    m["units"][u["id"]] = {"id": u["id"], "title": u["title"], "method": "consideration_line",
                                           "source": u["source"], "printed": u.get("printed", {}), "url": u.get("url", "")}
            for ev in r["removed"]:
                m["removed"][(ev["unit"], ev["kind"], ev["measure"])] = ev
            for h in r["held"]:
                m["held"][(h["unit"], h.get("kind", ""), h.get("measure", ""), h["why"][:40])] = h
            for h in r.get("notes", []):
                m["notes"][(h["unit"], h.get("measure", ""), h["tag"])] = h
            m["added"] = max(m["added"], r["added"])
            m["votes"].append(b["vote_date"])
            m["excluded"] += [e for e in excluded if e["day"] == day and e not in m["excluded"]]
        print(f"  [{i}/{len(plan)}] {b['bill_key']} {b['vote_date']}: kept text on {sorted(kept_days)}", flush=True)
    for (bk, day), m in merged.items():
        b = m["b"]
        kept_keys = {(uid, idx) for (_o, uid, idx) in m["paras"]}
        removed = [ev for ev in m["removed"].values() if not any((ev["unit"], i) in kept_keys for i in ev.get("idx", []))]
        if not any(not re.match(r"^[_\-=\s]{5,}$", t) for t, _ in m["paras"].values()):
            emptied.append({"bill_key": bk, "debate_date": day, "removed": removed})
            continue
        rows = [r for r in sorted(m["paras"].items()) if not re.match(r"^[_\-=\s]{5,}$", r[1][0])]   # item separators
        path = os.path.join(SEG_DIR, f"{bk}_{day}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(t for _, (t, _) in rows) + "\n")
        tags, tag_words, punits = [], Counter(), []
        for (_o, uid, _i), (t, tag) in rows:
            tag_words[tag] += len(t.split())
            if tags and tags[-1][0] == tag:
                tags[-1][1] += 1
            else:
                tags.append([tag, 1])
            if punits and punits[-1][0] == uid:
                punits[-1][1] += 1
            else:
                punits.append([uid, 1])
        used = {uid for (_o, uid, _i) in m["paras"]}
        spoken = any(tag in ("debate", "vehicle", "companion") and SEC.is_debate_speech(t) for _, (t, tag) in rows)
        index.append({**b, "debate_date": day, "date_source": m["src"],
                      "edition": (("daily" if day >= DAILY_FROM else "bound") if m["floor"] else b["edition"]),
                      "file": os.path.relpath(path, US),
                      "votes_served": sorted(set(m["votes"])),
                      "units": [u for uid, u in m["units"].items() if uid in used],
                      "para_tags": tags, "para_units": punits, "tag_words": dict(tag_words),
                      "no_debate": not spoken,
                      "added_paragraphs": m["added"],
                      "removed": [{k: v for k, v in ev.items() if k != "idx"} for ev in removed],
                      "held": [{k: (v[:600] if isinstance(v, str) else v) for k, v in h.items() if k != "idx"}
                               for h in m["held"].values()],
                      "notes": [{k: (v[:300] if isinstance(v, str) else v) for k, v in h.items() if k != "idx"}
                                for h in m["notes"].values()],
                      "excluded": m["excluded"]})
    dup = sum(len(m["votes"]) - 1 for m in merged.values())
    print(f"Bill-days reached from more than one vote, kept once: {sum(len(m['votes']) > 1 for m in merged.values())} "
          f"({dup} repeat entries merged)")
    save_json(index, INDEX, indent=1)
    save_json(missing, os.path.join(OUT, "segments_missing.json"), indent=1)
    save_json(emptied, os.path.join(OUT, "segments_emptied.json"), indent=1)
    print(f"Files written: {len(index)}; bill-votes not found: {len(missing)} (segments_missing.json); "
          f"bill-days left with no text: {len(emptied)} (segments_emptied.json)")
