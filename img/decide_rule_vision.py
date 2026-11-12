"""Rule + vision baseline on the Isaac pick-camera images (what a conventional induction cell does).
Order: barcode (zxing-cpp) -> colour checks for damage / hazmat diamond on the parcel region -> scale -> OCR (EasyOCR en+ko)
-> same address rules as the text rule baseline -> fallback MANUAL (= video coding by a person) or RESCAN if no text.
Thresholds fixed from the label/texture design before scoring (not tuned on results).  Output: img/pred_rule_vision_{set}.jsonl"""
import json, os, re, sys, time
import numpy as np
from PIL import Image
import zxingcpp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gen_parcels import CHUTES
import rule_baseline as rb
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CODE2CH = {f"{i+1:02d}": c for i, c in enumerate(CHUTES)}
_ocr = None

def ocr(img):
    global _ocr
    if _ocr is None:
        import easyocr; _ocr = easyocr.Reader(["ko", "en"], gpu=__import__("torch").cuda.is_available(), verbose=False)
    res = _ocr.readtext(np.asarray(img), rotation_info=[90, 180, 270], detail=1, paragraph=False)
    return " ".join(t for _, t, c in res if c > 0.2)

def parcel_mask(a):
    r, g, b = [a[..., k].astype(int) for k in range(3)]
    return (r > 150) & (g > 120) & (b > 70) & (r - b > 25)       # light cardboard under the camera light

def checks(a):
    m = parcel_mask(a); ys, xs = np.nonzero(m)
    if len(xs) < 1000: return {}, None
    y0, y1, x0, x1 = np.percentile(ys, 1), np.percentile(ys, 99), np.percentile(xs, 1), np.percentile(xs, 99)
    roi = a[int(y0):int(y1), int(x0):int(x1)].astype(int); r, g, b = roi[..., 0], roi[..., 1], roi[..., 2]
    area = roi.shape[0] * roi.shape[1]
    dark_brown = ((r < 140) & (r - b > 20) & (r >= g)).sum() / area          # wet stain / torn hole (not grey belt shadow)
    red = ((r > 150) & (g < 90) & (b < 90)).sum() / area                     # hazmat diamond outline
    return dict(dark_brown=round(float(dark_brown), 4), red=round(float(red), 5)), (int(x0), int(y0), int(x1), int(y1))

def decide(path, z):
    t = {}; t0 = time.perf_counter(); img = Image.open(path).convert("RGB"); a = np.asarray(img)
    t1 = time.perf_counter(); g = img.convert("L"); codes = []
    for ang in (0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90):   # omnidirectional scan (tunnel scanners read any orientation)
        codes = [c for c in zxingcpp.read_barcodes(g.rotate(ang, expand=True) if ang else g) if c.text.startswith("KR")]
        if codes: break
    t["barcode_s"] = time.perf_counter() - t1
    sc = None
    for c in codes:
        m = re.match(r"KR\d{10}(\d\d)$", c.text)
        if m and m.group(1) in CODE2CH: sc = CODE2CH[m.group(1)]
    t1 = time.perf_counter(); f, box = checks(a); t["checks_s"] = time.perf_counter() - t1
    ev = dict(barcode=sc, **f)
    if f.get("dark_brown", 0) > 0.04: return "REJECT", ev, t, time.perf_counter() - t0
    if f.get("red", 0) > 0.0015 or z["weight"] > 30: return "MANUAL", ev, t, time.perf_counter() - t0
    if sc: return sc, ev, t, time.perf_counter() - t0
    crop = img.crop(box) if box else img
    t1 = time.perf_counter(); text = ocr(crop); t["ocr_s"] = time.perf_counter() - t1; ev["ocr"] = text[:300]
    if not text.strip(): return "RESCAN", ev, t, time.perf_counter() - t0
    obs = {"ocr_label": text, "barcode": "no read", "weight_kg": z["weight"], "vision_flags": "no visible issue"}
    pred = rb.rule(obs)
    if pred == "MANUAL" and len(re.sub(r"[^A-Za-z가-힣0-9]", "", text)) < 12: pred = "RESCAN"
    return pred, ev, t, time.perf_counter() - t0

def main():
    for s in sys.argv[1:] or ["stream", "hard"]:
        rows = [json.loads(l) for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8")]
        out = os.path.join(HERE, f"pred_rule_vision_{s}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for z in rows:
                p = os.path.join(ROOT, "cam", f"{z['id']}.png")
                if not os.path.exists(p): continue
                pred, ev, t, dt = decide(p, z)
                f.write(json.dumps(dict(id=z["id"], pred=pred, gold=z["action"], exc=z["exc"], form=z["form"], barcode=z["barcode"],
                                        latency_s=round(dt, 3), stages={k: round(v, 3) for k, v in t.items()}, evidence=ev), ensure_ascii=False) + "\n")
                print(z["id"], pred, z["action"], round(dt, 2), flush=True)

if __name__ == "__main__":
    main()
