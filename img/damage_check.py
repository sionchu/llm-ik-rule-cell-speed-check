"""Fast local damage check for the parcel cell (v2 pipeline, 2026-11-12).
Feature: inside the parcel crop (same ROI crop the LLMs see), fraction of pixels that are clearly darker than the carton's own
median brightness AND brownish (r-b > 18) -> wet stains / torn holes; black label text (r~g~b) and the white label are excluded.
Threshold is calibrated on the stream set only and then applied unchanged to hard (held-out).
Usage: python img/damage_check.py  -> img/damage_feat_{stream,hard}.json"""
import json, os, sys, tempfile, time
import numpy as np
from PIL import Image
os.environ["ROI"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import decide_llm_image as D


def feat(png):
    w = tempfile.mkdtemp(); D.to_jpeg(png, os.path.join(w, "view.jpg"))
    a = np.asarray(Image.open(os.path.join(w, "view.jpg")).convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]; L = 0.299 * r + 0.587 * g + 0.114 * b
    card = (r - b > 30) & (L > 120)                       # cardboard pixels
    red2 = float(((r > 200) & (r - g > 80) & (r - b > 70)).mean())   # hazmat diamond outline (red on white label, rendered pinkish)
    if card.sum() < 500: return 0.0, 0.0, red2
    med = float(np.median(L[card]))
    dark_brown = (L < 0.72 * med) & (r - b > 18) & (r > g)
    vdark = (L < 0.40 * med) & (np.abs(r - b) < 40) & ~((np.abs(r - g) < 8) & (np.abs(g - b) < 8))
    n = a.shape[0] * a.shape[1]
    return float(dark_brown.mean()), float(vdark.mean()), red2


if __name__ == "__main__":
    for s in sys.argv[1:] or ["stream", "hard"]:
        out = {}
        for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8"):
            z = json.loads(l); t0 = time.perf_counter()
            f1, f2, f3 = feat(os.path.join(ROOT, "cam", f"{z['id']}.png"))
            out[z["id"]] = dict(dark_brown=f1, very_dark=f2, red2=f3, s=time.perf_counter() - t0, exc=z["exc"])
        json.dump(out, open(os.path.join(HERE, f"damage_feat_{s}.json"), "w"), indent=0)
        dm = sorted(v["dark_brown"] for v in out.values() if v["exc"].startswith("damaged")); ok = sorted(v["dark_brown"] for v in out.values() if not v["exc"].startswith("damaged"))
        dm2 = sorted(v["very_dark"] for v in out.values() if v["exc"].startswith("damaged")); ok2 = sorted(v["very_dark"] for v in out.values() if not v["exc"].startswith("damaged"))
        print(s, "dark_brown dmg", [round(x, 4) for x in dm], "ok top5", [round(x, 4) for x in ok[-5:]])
        hz = sorted(v["red2"] for v in out.values() if v["exc"] == "hazmat"); nh = sorted(v["red2"] for v in out.values() if v["exc"] != "hazmat")
        print(s, "red2 hazmat", [round(x, 5) for x in hz], "other top5", [round(x, 5) for x in nh[-5:]])
        print(s, "very_dark  dmg", [round(x, 4) for x in dm2], "ok top5", [round(x, 4) for x in ok2[-5:]], "median s", round(float(np.median([v['s'] for v in out.values()])), 3))
