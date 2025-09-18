
import argparse
import json
import os
import re
from collections import defaultdict
from typing import Dict, Optional

CALL_RE = r"[A-Za-z0-9/]+(?:-[0-9]{1,2})?"

PARENT_RE = re.compile(
    rf"^\s*\.\.\s*<\s*(?P<call>{CALL_RE})\s*>\s*(?:[^0-9\-+]*(?P<snr>[-+]?\d+(?:\.\d+)?)\s*(?:dB|db)?)?",
    re.IGNORECASE
)

CHILD_RE = re.compile(
    rf"^\s*/\s*(?P<call>{CALL_RE})\s*(?:[^0-9\-+]*(?P<snr>[-+]?\d+(?:\.\d+)?)\s*(?:dB|db)?)?",
    re.IGNORECASE
)

def norm_call(cs: str) -> str:
    cs = (cs or "").strip().upper()
    return re.sub(r"[^\w/\-]+$", "", cs)

def parse_log(path: str, mycall: str) -> Dict:
    heard: Dict[str, dict] = {}
    current_parent: Optional[str] = None

    parent_snr = defaultdict(lambda: None)
    child_snr: Dict[str, Dict[str, Optional[float]]] = defaultdict(lambda: defaultdict(lambda: None))

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            mp = PARENT_RE.match(line)
            if mp:
                p = norm_call(mp.group("call"))
                current_parent = p
                snr_txt = mp.group("snr")
                if snr_txt is not None:
                    try:
                        snr_val = float(snr_txt)
                        parent_snr[p] = snr_val if parent_snr[p] is None else max(parent_snr[p], snr_val)
                    except Exception:
                        pass
                if p not in heard:
                    heard[p] = {}
                continue

            mc = CHILD_RE.match(line)
            if mc and current_parent:
                c = norm_call(mc.group("call"))
                snr_txt = mc.group("snr")
                if snr_txt is not None:
                    try:
                        snr_val = float(snr_txt)
                        prev = child_snr[current_parent][c]
                        child_snr[current_parent][c] = snr_val if prev is None else max(prev, snr_val)
                    except Exception:
                        pass
                if current_parent not in heard:
                    heard[current_parent] = {}
                heard[current_parent].setdefault("children", {})
                heard[current_parent]["children"].setdefault(c, {})
                continue

    out = {"mycall": mycall, "heard": {}}
    for p, payload in heard.items():
        entry = {}
        if parent_snr[p] is not None:
            entry["snr"] = round(parent_snr[p], 1)
        if "children" in payload:
            kids = {}
            for c in payload["children"].keys():
                kentry = {}
                snr_val = child_snr[p][c]
                if snr_val is not None:
                    kentry["snr"] = round(snr_val, 1)
                kids[c] = kentry
            entry["children"] = kids
        out["heard"][p] = entry

    return out

def merge_graph(existing: Dict, new: Dict, mycall: str) -> Dict:
    out = {"mycall": mycall, "heard": {}}
    ex_heard = existing.get("heard", {}) if isinstance(existing, dict) else {}
    new_heard = new.get("heard", {}) if isinstance(new, dict) else {}

    for p, pdata in ex_heard.items():
        out["heard"][p] = {}
        if "snr" in pdata:
            out["heard"][p]["snr"] = pdata["snr"]
        if "children" in pdata and isinstance(pdata["children"], dict):
            out["heard"][p]["children"] = { c: (v if isinstance(v, dict) else {}) for c, v in pdata["children"].items() }

    for p, pdata in new_heard.items():
        if p not in out["heard"]:
            out["heard"][p] = {}
        if "snr" in pdata:
            ns = pdata["snr"]
            es = out["heard"][p].get("snr")
            out["heard"][p]["snr"] = ns if es is None else max(es, ns)
        nchildren = pdata.get("children", {})
        if nchildren:
            out["heard"][p].setdefault("children", {})
            for c, cdata in nchildren.items():
                if c not in out["heard"][p]["children"]:
                    out["heard"][p]["children"][c] = {}
                if "snr" in cdata:
                    ns = cdata["snr"]
                    es = out["heard"][p]["children"][c].get("snr")
                    out["heard"][p]["children"][c]["snr"] = ns if es is None else max(es, ns)

    return out

def main():
    ap = argparse.ArgumentParser(description="Generate or update link_graph.json from beacon logs")
    ap.add_argument("--input", required=True, help="Path to beacon log text file")
    ap.add_argument("--output", default="./store/link_graph.json", help="Output JSON path (default: ./store/link_graph.json)")
    ap.add_argument("--mycall", required=True, help="Your callsign (center node)")
    ap.add_argument("--mode", choices=["append", "overwrite"], default="append", help="Append (merge) or overwrite the output file (default: append)")
    args = ap.parse_args()

    new_data = parse_log(args.input, args.mycall.upper())

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    if args.mode == "overwrite" or not os.path.exists(args.output):
        final = new_data
    else:
        try:
            with open(args.output, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {"mycall": args.mycall.upper(), "heard": {}}
        final = merge_graph(existing, new_data, args.mycall.upper())

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(final, f, indent=2)
    print(f"Wrote {args.output} (mode: {args.mode})")

if __name__ == "__main__":
    main()
