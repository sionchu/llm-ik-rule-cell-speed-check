import json, re, time
from gen_parcels import CHUTES, EXC, ACTIONS, PLAN, PLACES

def load(split):
    return [json.loads(l) for l in open(f"parcels_{split}.jsonl", encoding="utf-8")]

def state_text(o):
    return (f"Parcel on the induction conveyor of a robot sorting cell. OCR of shipping label: \"{o['ocr_label']}\". "
            f"Barcode scanner: {o['barcode']}. Scale: {o['weight_kg']} kg. Size: {o['dims_cm'][0]}x{o['dims_cm'][1]}x{o['dims_cm'][2]} cm. "
            f"Camera inspection: {o['vision_flags']}.")

def criteria():
    c = {}
    for ch in CHUTES:
        city, d = PLACES[ch]
        c[ch] = f"Chute {ch}: postal codes starting {', '.join(PLAN[ch])}; {city} ({', '.join(d)})"
    c["RESCAN"] = "Send back to rescan: the label text is unreadable or empty and the barcode did not read"
    c["MANUAL"] = ("Manual handling desk: over 30 kg, hazardous-goods label, postal code contradicts the written city, "
                   "or the destination cannot be determined")
    c["REJECT"] = "Reject lane: the package is visibly damaged (torn, crushed, leaking, wet)"
    return c

POLICY = ("Rules: damaged -> REJECT. Over 30 kg or hazardous-goods label -> MANUAL. If the barcode read OK, use its sort code. "
          "Otherwise route by the postal code prefix or the written city/district. If postal code and written city disagree -> MANUAL. "
          "Unreadable label and no barcode -> RESCAN. Destination impossible to determine -> MANUAL.")

def score(rows, preds):
    from collections import defaultdict
    by = defaultdict(lambda: [0, 0])
    for r, p in zip(rows, preds):
        k = r["kind"].split(":")[0] if not r["kind"].startswith("alias") else r["kind"]
        by[k][0] += p == r["action"]; by[k][1] += 1
        by["ALL"][0] += p == r["action"]; by["ALL"][1] += 1
    return {k: f"{a}/{n}" for k, (a, n) in sorted(by.items())}
