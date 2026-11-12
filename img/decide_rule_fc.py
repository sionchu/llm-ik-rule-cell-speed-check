"""FC outbound-check rule baseline (common industry practice): order barcode scan vs order, colour damage check,
weight tolerance +-5%, fragile-sticker check (red FRAGILE sticker template = the sticker this FC is assumed to use).
Thresholds fixed before scoring. Output: img/pred_rule_fc_{set}.jsonl"""
import json, os, re, sys, time
import numpy as np
from PIL import Image
import zxingcpp
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from decide_rule_vision import checks


def decode(img):
    g = img.convert("L")
    for ang in (0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90):
        for c in zxingcpp.read_barcodes(g.rotate(ang, expand=True) if ang else g):
            m = re.match(r"ORD(\d{12})$", c.text)
            if m: return m.group(1)
    return None


def red_sticker(a, box):
    if box is None: return 0.0
    x0, y0, x1, y1 = box; roi = a[y0:y1, x0:x1].astype(int); r, g, b = roi[..., 0], roi[..., 1], roi[..., 2]
    # v2: calibrated on rendered pixels (_redcal.py: sticker renders ~(242,101,110) under the cell light; v1 test g<90 never fired)
    return float(((r > 225) & (r - g > 100) & (r - b > 90)).mean())


def decide(path, z):
    t = {}; t0 = time.perf_counter(); img = Image.open(path).convert("RGB"); a = np.asarray(img)
    t1 = time.perf_counter(); code = decode(img); t["barcode_s"] = time.perf_counter() - t1
    t1 = time.perf_counter(); f, box = checks(a); red = red_sticker(a, box); t["checks_s"] = time.perf_counter() - t1
    o = z["order"]; dev = abs(z["weight"] - o["expected_kg"]) / o["expected_kg"]
    ev = dict(code=code, match=(code == o["order_no"]) if code else None, dark_brown=f.get("dark_brown"), red=round(red, 5), weight_dev=round(dev, 3))
    if code and code != o["order_no"]: p = "MANUAL"
    elif f.get("dark_brown", 0) > 0.04: p = "DAMAGED"
    elif dev > 0.05: p = "SPEC_OUT"
    elif not code: p = "RELABEL"
    elif o["fragile"] and red < 0.002: p = "PACK_UNFIT"
    else: p = "OK"
    return p, ev, t, time.perf_counter() - t0


def main():
    for s in sys.argv[1:]:
        rows = [json.loads(l) for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8")]
        out = os.path.join(HERE, f"pred_rule_fc_{s}.jsonl"); open(out, "w").close()
        for z in rows:
            p, ev, t, dt = decide(os.path.join(ROOT, "cam", f"{z['id']}.png"), z)
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(dict(id=z["id"], pred=p, gold=z["action"], exc=z["exc"], form=z["sticker"], barcode=z["barcode"],
                                         latency_s=round(dt, 3), stages={k: round(v, 3) for k, v in t.items()}, evidence=ev), ensure_ascii=False) + "\n")
            print(z["id"], p, z["action"], round(dt, 2), flush=True)


if __name__ == "__main__":
    main()
