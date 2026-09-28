#!/usr/bin/env python3
"""
patch_sheet_remove_days.py
Edits the finished review workbooks instead of rebuilding them. It takes out every
bill-day in data/v3_exclusions.json that an official record confirms (the same check
apply_exclusions.py uses) and leaves every other cell, colour, link, column width and
filter as the builder wrote it.

  outputs/health_bills_review.xlsx
     Bills + Sitting Days   those bill-day rows removed; predications_bill_total lowered
                            for the same bill by the predications of the removed day
     All Predications       the predications of those bill-days removed
     Health list decisions  a bill is removed only if it has no predications left
     Excluded bill-days     rewritten from the official checks, as the builder does
  outputs/transcripts_{us,ontario,quebec}.xlsx
     the paragraphs of those bill-days removed

Each file is written to a new file and checked before it replaces the old one:
  - no removed bill-day is left
  - each sheet lost exactly the rows it should have
  - predications_this_day and predications_bill_total match a recount of All Predications,
    and the health list holds exactly the bills that still have predications
  - links, read straight from the file's XML: each one sits on the cell whose text is that
    link, and the only links gone are the ones on removed rows
If a check fails nothing is replaced. The old file is kept as *_before_patch_<time>.xlsx.

Run from project root after the builder has finished:
    python3 scripts/v3/patch_sheet_remove_days.py
"""
import datetime as dt, os, re, subprocess, sys, time, zipfile
from collections import Counter, defaultdict
from copy import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import coordinate_from_string, column_index_from_string

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import apply_exclusions as AE          # the same official-record check that removes the data rows
import build_review_excel as B         # the builder's own styles and text cleaning

ROOT = HERE.parent.parent
OUT = ROOT / "outputs"
STAMP = dt.datetime.now().strftime("%Y%m%d-%H%M")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


def say(msg):
    print(msg, flush=True)


def iso(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return "" if v is None else str(v)


def attrs(tag_text):
    return dict(re.findall(r'([\w:]+)="([^"]*)"', tag_text))


def builder_running():
    """True while a python process is running build_review_excel.py (it may still be writing)."""
    try:
        r = subprocess.run(["pgrep", "-f", r"^[^ ]*[Pp]ython[^ ]* [^ ]*build_review_excel\.py"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return bool(r.stdout.split())


# ---------------------------------------------------------------- reading the file's own XML
def sheet_paths(zf):
    wbx = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    tgt = {r.get("Id"): r.get("Target") for r in rels.findall("pr:Relationship", NS)}
    out = {}
    for s in wbx.find("m:sheets", NS):
        t = tgt[s.get("{%s}id" % NS["r"])].lstrip("/")
        out[s.get("name")] = t if t.startswith("xl/") else "xl/" + t
    return out


def scan_xml(zf, member):
    """(text before <sheetData>, text from <hyperlinks> on, whether an autoFilter is set)."""
    head, found, tail, links, has_filter = b"", False, b"", None, False
    with zf.open(member) as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            if not found:
                head += chunk
                i = head.find(b"<sheetData")
                if i < 0:
                    continue
                found = True
                chunk, head = head[i:], head[:i]
            buf = tail + chunk
            if links is None:
                i = buf.find(b"<hyperlinks")
                if i >= 0:
                    links = buf[i:]
                if b"<autoFilter" in buf:
                    has_filter = True
                tail = buf[-64:]
            else:
                links += chunk
                if b"<autoFilter" in chunk:
                    has_filter = True
    if links is not None and b"<autoFilter" in links:
        has_filter = True
    return head.decode("utf-8", "ignore"), (links or b"").decode("utf-8", "ignore"), has_filter


def layouts(path):
    """Column widths, frozen pane, gridlines and filter of every sheet, read from the file."""
    out = {}
    with zipfile.ZipFile(path) as zf:
        for name, member in sheet_paths(zf).items():
            h, _, has_filter = scan_xml(zf, member)
            widths = {}
            for c in re.findall(r"<col\s([^>]*?)/?>", h):
                a = attrs(c)
                if "width" in a:
                    lo = int(a.get("min", 1))
                    for i in range(lo, int(a.get("max", lo)) + 1):
                        widths[get_column_letter(i)] = float(a["width"])
            freeze = None
            for p in re.findall(r"<pane\s([^>]*?)/?>", h):
                a = attrs(p)
                if a.get("state") in ("frozen", "frozenSplit"):
                    freeze = a.get("topLeftCell")
            sv = re.search(r"<sheetView\s([^>]*?)/?>", h)
            grid = not (sv and attrs(sv.group(1)).get("showGridLines") in ("0", "false"))
            out[name] = {"widths": widths, "freeze": freeze, "grid": grid, "filter": has_filter}
    return out


def raw_links(path):
    """{sheet: {cell ref: link target}} straight from the <hyperlink> elements and their
    relationship files, without the spreadsheet library."""
    out = {}
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for name, member in sheet_paths(zf).items():
            d, f = member.rsplit("/", 1)
            relp = f"{d}/_rels/{f}.rels"
            rid = {}
            if relp in names:
                for r in ET.fromstring(zf.read(relp)).findall("pr:Relationship", NS):
                    rid[r.get("Id")] = r.get("Target")
            _, links, _ = scan_xml(zf, member)
            got = {}
            for h in re.findall(r"<hyperlink\s([^>]*?)/?>", links):
                a = attrs(h)
                got[a.get("ref")] = rid.get(a.get("r:id") or a.get("id"), "")
            out[name] = got
    return out


def rc(ref):
    col, row = coordinate_from_string(ref)
    return row, column_index_from_string(col)


# ---------------------------------------------------------------- copying cells (value, style, link)
class Copier:
    def __init__(self):
        self.cache = {}

    def cell(self, ws, c, value=None, use_value=False):
        v = value if use_value else c.value
        wc = WriteOnlyCell(ws, value=v)
        if getattr(c, "has_style", False):
            key = getattr(c, "_style_id", None)
            if key is None:
                key = tuple(c.style_array)
            arr = self.cache.get(key)
            if arr is None:
                wc.font, wc.fill, wc.border = copy(c.font), copy(c.fill), copy(c.border)
                wc.alignment, wc.protection = copy(c.alignment), copy(c.protection)
                wc.number_format = c.number_format
                self.cache[key] = copy(wc._style)
            else:
                wc._style = copy(arr)
            # the builder links a cell only together with the underlined link font, and
            # only when the cell text is the URL itself
            if isinstance(v, str) and v.startswith("http") and c.font is not None and c.font.u:
                wc.hyperlink = v
        return wc


def new_sheet(wb, name, lay):
    ws = wb.create_sheet(name)
    for letter, w in lay["widths"].items():
        ws.column_dimensions[letter].width = w
    if lay["freeze"]:
        ws.freeze_panes = lay["freeze"]
    if not lay["grid"]:
        ws.sheet_view.showGridLines = False
    return ws


def finish_sheet(ws, lay, n_rows, n_cols):
    if lay["filter"] and n_rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(max(n_cols, 1))}{n_rows}"


# ---------------------------------------------------------------- checks on a saved file
def read_rows(path, key_cols, refs):
    """Row keys per sheet, row counts, and the cell text at each linked cell."""
    need = defaultdict(lambda: defaultdict(list))
    for name, rr in refs.items():
        for ref in rr:
            r, c = rc(ref)
            need[name][r].append((c, ref))
    rb = openpyxl.load_workbook(path, read_only=True)
    keys, text, rows = {}, {}, {}
    for name in rb.sheetnames:
        it = rb[name].iter_rows(values_only=True)
        hdr = list(next(it, []) or [])
        idx = [hdr.index(k) for k in key_cols.get(name, []) if k in hdr]
        ks, tx, n = [], {}, 0
        for n, row in enumerate(it, 2):
            if idx:
                ks.append(tuple(iso(row[i]) if i < len(row) else "" for i in idx))
            for c, ref in need[name].get(n, ()):
                tx[ref] = row[c - 1] if c - 1 < len(row) else None
        keys[name], text[name], rows[name] = ks, tx, max(n - 1, 0)
    rb.close()
    return keys, text, rows


def link_checks(old_path, new_path, dropped_rows, new_text, new_links):
    fails = []
    old_links = raw_links(old_path)
    for name, links in new_links.items():
        for ref, url in links.items():
            if new_text[name].get(ref) != url:
                fails.append(f"{name} {ref}: link {url[:70]} sits on a cell reading {str(new_text[name].get(ref))[:70]}")
        ol = old_links.get(name, {})
        gone_links = sum(1 for ref in ol if rc(ref)[0] in dropped_rows.get(name, ()))
        if len(links) != len(ol) - gone_links:
            fails.append(f"{name}: {len(links):,} links in the new file; expected {len(ol) - gone_links:,} "
                         f"({len(ol):,} before, {gone_links} on removed rows)")
        if ol or links:
            say(f"  {name}: {len(links):,} links, each on the cell holding that URL "
                f"({len(ol):,} before, {gone_links} of them on removed rows)")
    return fails


# ---------------------------------------------------------------- main workbook
def patch_main(gone, checked):
    src = OUT / "health_bills_review.xlsx"
    if not src.exists():
        sys.exit(f"not found: {src}")
    tmp = src.with_name(src.stem + "_patching.xlsx")
    lay = layouts(src)
    rb = openpyxl.load_workbook(src, read_only=True)
    names = rb.sheetnames
    for need in ("Bills + Sitting Days", "All Predications", "Health list decisions", "Excluded bill-days"):
        if need not in names:
            sys.exit(f"sheet '{need}' not found in {src.name}; is this the builder's workbook?")

    # how many predications each removed day had, per bill (from the Bills sheet)
    it = rb["Bills + Sitting Days"].iter_rows(values_only=True)
    hdr = list(next(it))
    ij, ib, idd, ipd = (hdr.index(x) for x in ("jurisdiction", "bill_key", "sitting_date", "predications_this_day"))
    lost = Counter()
    for r in it:
        if (r[ij], r[ib], iso(r[idd])) in gone:
            lost[(r[ij], r[ib])] += int(r[ipd] or 0)

    wb = openpyxl.Workbook(write_only=True)
    cp = Copier()
    removed = defaultdict(Counter)
    dropped_rows = defaultdict(set)
    pred_bill = Counter()
    new_totals = {}
    for name in names:
        out = new_sheet(wb, name, lay[name])
        it = rb[name].iter_rows()
        first = next(it, None)
        if first is None:
            continue
        hdr = [c.value for c in first]
        out.append([cp.cell(out, c) for c in first])
        n_out = 1
        if name == "Excluded bill-days":
            # the same rows the builder writes from exclusions_applied.csv
            for r, ok, note in checked:
                vals = {"status": "REMOVED" if ok else "HELD", "jurisdiction": r["jurisdiction"],
                        "bill_key": r["bill_key"], "date": r.get("date", "*"), "reason": r.get("reason", ""),
                        "official_check": note}
                cells = []
                for ci, h in enumerate(hdr, 1):
                    wc = WriteOnlyCell(out, value=B.clean(vals.get(h, "")))
                    if ci == 1 and not ok:
                        wc.fill = B.BAD
                    cells.append(wc)
                out.append(cells)
                n_out += 1
            finish_sheet(out, lay[name], n_out, len(first))
            continue
        kj = hdr.index("jurisdiction") if "jurisdiction" in hdr else None
        kb = hdr.index("bill_key") if "bill_key" in hdr else None
        kd = hdr.index("sitting_date") if name == "Bills + Sitting Days" else (
            hdr.index("date") if name == "All Predications" else None)
        kt = hdr.index("predications_bill_total") if name == "Bills + Sitting Days" else None
        for n, row in enumerate(it, 2):
            if name in ("Bills + Sitting Days", "All Predications"):
                k = (row[kj].value, row[kb].value, iso(row[kd].value))
                if k in gone:
                    removed[name][k] += 1
                    dropped_rows[name].add(n)
                    continue
                if name == "All Predications":
                    pred_bill[k[:2]] += 1
            elif name == "Health list decisions":
                k = (row[kj].value, row[kb].value)
                if k in lost and pred_bill.get(k, 0) == 0:
                    removed[name][k] += 1
                    dropped_rows[name].add(n)
                    continue
            cells = []
            for ci, c in enumerate(row):
                if ci == kt and (k[0], k[1]) in lost:
                    t = int(c.value or 0) - lost[(k[0], k[1])]
                    new_totals[(k[0], k[1])] = t
                    cells.append(cp.cell(out, c, value=t, use_value=True))
                else:
                    cells.append(cp.cell(out, c))
            out.append(cells)
            n_out += 1
        finish_sheet(out, lay[name], n_out, len(first))
    rb.close()

    for name in ("Bills + Sitting Days", "All Predications", "Health list decisions"):
        for k, n in sorted(removed[name].items()):
            say(f"  {name}: removed {n} row(s) for {' '.join(map(str, k))}")
    for (j, bk), n in sorted(lost.items()):
        if (j, bk) in new_totals:
            say(f"  {j} {bk}: predications_bill_total on its other day(s) lowered by {n} to {new_totals[(j, bk)]}")
        else:
            say(f"  {j} {bk}: no other sitting day for this bill, so it has no rows left")
    if not any(removed.values()):
        discard(wb)
        say("  no removed bill-day is in this workbook; nothing to change")
        return None
    # the arithmetic above must agree with the predication rows actually removed and kept
    problems = [f"{j} {bk}: bill total {t} but {pred_bill.get((j, bk), 0)} predication rows remain"
                for (j, bk), t in new_totals.items() if t != pred_bill.get((j, bk), 0)]
    if sum(lost.values()) != sum(removed["All Predications"].values()):
        problems.append(f"the Bills sheet counts {sum(lost.values())} predications on the removed days; "
                        f"All Predications had {sum(removed['All Predications'].values())}")
    if problems:
        discard(wb)
        say("STOPPED, nothing replaced. The counts do not agree:")
        for p in problems:
            say("  " + p)
        sys.exit(1)
    say("  saving the new workbook ...")
    wb.save(tmp)
    return src, tmp, removed, dropped_rows


def check_main(src, tmp, gone, removed, dropped_rows):
    say("  checking the saved file ...")
    new_links = raw_links(tmp)
    key_cols = {"Bills + Sitting Days": ["jurisdiction", "bill_key", "sitting_date", "predications_this_day",
                                         "predications_bill_total"],
                "All Predications": ["jurisdiction", "bill_key", "date"],
                "Health list decisions": ["jurisdiction", "bill_key"]}
    keys, text, rows = read_rows(tmp, key_cols, new_links)
    _, _, old_rows = read_rows(src, {}, {})
    fails = []
    for name in ("Bills + Sitting Days", "All Predications"):
        left = sum(1 for k in keys[name] if tuple(k[:3]) in gone)
        if left:
            fails.append(f"{name}: {left} row(s) of a removed bill-day are still there")
    for name in old_rows:
        exp = old_rows[name] - sum(removed[name].values()) if name != "Excluded bill-days" else rows[name]
        if rows[name] != exp:
            fails.append(f"{name}: {rows[name]:,} rows, expected {exp:,}")
    day, bill = Counter(), Counter()
    for j, bk, d in keys["All Predications"]:
        day[(j, bk, d)] += 1
        bill[(j, bk)] += 1
    mism = [k for k in keys["Bills + Sitting Days"]
            if int(k[3] or 0) != day.get(k[:3], 0) or int(k[4] or 0) != bill.get(k[:2], 0)]
    if mism:
        fails.append(f"Bills + Sitting Days: {len(mism)} row(s) whose predication counts differ from a "
                     f"recount of All Predications, e.g. {mism[:3]}")
    hl = set(keys["Health list decisions"])
    if hl != set(bill):
        fails.append(f"Health list decisions: {len(hl - set(bill))} bill(s) with no predications listed, "
                     f"{len(set(bill) - hl)} bill(s) with predications missing")
    say(f"  rows: " + ", ".join(f"{n} {rows[n]:,} (was {old_rows[n]:,})" for n in rows if n != "README"))
    fails += link_checks(src, tmp, dropped_rows, text, new_links)
    return fails


# ---------------------------------------------------------------- transcripts
def patch_transcript(j, gone_j):
    src = OUT / f"transcripts_{j}.xlsx"
    if not src.exists():
        say(f"  transcripts_{j}.xlsx not found, skipped")
        return None
    lay = layouts(src)
    rb = openpyxl.load_workbook(src, read_only=True)
    tmp = src.with_name(src.stem + "_patching.xlsx")
    wb = openpyxl.Workbook(write_only=True)
    cp = Copier()
    hits, dropped_rows, old_n = Counter(), defaultdict(set), 0
    for name in rb.sheetnames:
        out = new_sheet(wb, name, lay[name])
        it = rb[name].iter_rows()
        first = next(it, None)
        if first is None:
            continue
        hdr = [c.value for c in first]
        out.append([cp.cell(out, c) for c in first])
        n_out = 1
        ib, idd = hdr.index("bill_key"), hdr.index("sitting_date")
        for n, row in enumerate(it, 2):
            old_n += 1
            k = (row[ib].value, iso(row[idd].value))
            if k in gone_j:
                hits[k] += 1
                dropped_rows[name].add(n)
                continue
            out.append([cp.cell(out, c) for c in row])
            n_out += 1
        finish_sheet(out, lay[name], n_out, len(first))
    rb.close()
    if not hits:
        discard(wb)
        say("  no removed bill-day in it, left as is")
        return None
    wb.save(tmp)
    for k, n in sorted(hits.items()):
        say(f"  removed {n:,} paragraph(s) for {k[0]} {k[1]}")
    new_links = raw_links(tmp)
    names = list(new_links)
    keys, text, rows = read_rows(tmp, {n: ["bill_key", "sitting_date"] for n in names}, new_links)
    fails = []
    left = sum(1 for n in names for k in keys[n] if k in gone_j)
    if left:
        fails.append(f"{left} paragraph(s) of a removed bill-day still there")
    if sum(rows.values()) != old_n - sum(hits.values()):
        fails.append(f"{sum(rows.values()):,} rows, expected {old_n - sum(hits.values()):,}")
    fails += link_checks(src, tmp, dropped_rows, text, new_links)
    return src, tmp, fails


def discard(wb):
    """Throw away an unsaved write-only workbook cleanly (no temp files left behind)."""
    for ws in wb.worksheets:
        try:
            ws.close()
            ws._writer.cleanup()
        except Exception:
            pass


def swap(src, tmp):
    bak = src.with_name(f"{src.stem}_before_patch_{STAMP}.xlsx")
    os.replace(src, bak)
    os.replace(tmp, src)
    return bak


def main():
    if builder_running():
        sys.exit("build_review_excel.py is still running. Run this after it prints 'Saved ... transcripts_quebec.xlsx'.")
    t0 = time.time()
    checked = [(r,) + tuple(AE.verify(r)) for r in AE.load_exclusions()]
    gone = {(r["jurisdiction"], r["bill_key"], r["date"]) for r, ok, _ in checked if ok and r.get("date", "*") != "*"}
    say(f"{len(gone)} bill-days confirmed against an official record; "
        f"{sum(1 for _, ok, _ in checked if not ok)} held and not touched")

    say("health_bills_review.xlsx")
    res = patch_main(gone, checked)
    if res:
        src, tmp, removed, dropped_rows = res
        fails = check_main(src, tmp, gone, removed, dropped_rows)
        if fails:
            say("STOPPED, the workbook was NOT replaced. Problems in the new file:")
            for f in fails[:30]:
                say("  " + f)
            say(f"  (the new file is left as {tmp.name} for a look)")
            sys.exit(1)
        bak = swap(src, tmp)
        say(f"  all checks passed; replaced. The old one is {bak.name}")
        say(f"  ({time.time() - t0:.0f}s) health_bills_review.xlsx is ready to send.")

    for j in B.JURS:
        gj = {(bk, d) for jj, bk, d in gone if jj == j}
        if not gj:
            continue
        say(f"transcripts_{j}.xlsx")
        res = patch_transcript(j, gj)
        if res is None:
            continue
        s, t, f = res
        if f:
            say(f"  STOPPED, transcripts_{j}.xlsx NOT replaced:")
            for x in f[:30]:
                say("    " + x)
            continue
        b = swap(s, t)
        say(f"  all checks passed; replaced. The old one is {b.name}")
    say(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
