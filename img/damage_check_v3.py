"""Wet-stain colour feature (v3, 2026-11-12). Fixes v2 dark_brown, which compared pixels to the carton's *median* brightness:
when stains cover a large part of the lid the median itself is stain-coloured, so heavy wet stains scored ~0 (stream_0172 db 0.008).
v3 uses absolute colour of the spread stain instead of relative darkness:
  stain  = mid brightness (145<L<195), brownish (r-g>25, r-b>55), not yellow (g-b<50)  -> water-soaked cardboard
  hole   = grey-brown inside of the box (85<L<150, slightly warm, low saturation)     -> torn opening
  (a first 'very dark' hole version failed: belt shadows are darker than the opening)
Values are fractions of the ROI crop (same crop the LLMs see). Thresholds are chosen on stream, then applied to hard unchanged.
Usage: python img/damage_check_v3.py -> img/damage_feat3_{stream,hard}.json"""
import json, os, sys, tempfile, time
import numpy as np
from PIL import Image
os.environ["ROI"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import decide_llm_image as D

def feat(png):
    w = tempfile.mkdtemp(); D.to_jpeg(png, os.path.join(w, "view.jpg"))
    im = Image.open(os.path.join(w, "view.jpg")).convert("RGB"); im.thumbnail((768, 768))   # downsample: same ratios, ~10x faster
    a = np.asarray(im).astype(np.int32); r, g, b = a[..., 0], a[..., 1], a[..., 2]
    L = (299 * r + 587 * g + 114 * b) // 1000
    stain = (L > 145) & (L < 195) & (r - g > 25) & (r - b > 55) & (g - b < 50)
    hole = (L > 85) & (L < 150) & (r - b >= 12) & (r - b <= 50) & (r - g >= 4) & (r - g <= 28) & (g - b >= 3) & (g - b <= 28)
    return float(stain.mean()), float(hole.mean())

if __name__ == "__main__":
    for s in sys.argv[1:] or ["stream", "hard"]:
        out = {}
        for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8"):
            z = json.loads(l); t0 = time.perf_counter()
            f1, f2 = feat(os.path.join(ROOT, "cam", f"{z['id']}.png"))
            out[z["id"]] = dict(stain=f1, hole=f2, s=time.perf_counter() - t0, exc=z["exc"])
        json.dump(out, open(os.path.join(HERE, f"damage_feat3_{s}.json"), "w"), indent=0)
        for k in ("stain", "hole"):
            for e in ("damaged_wet", "damaged_torn"):
                print(s, k, e, sorted(round(v[k], 4) for v in out.values() if v["exc"] == e))
            print(s, k, "others top6", sorted(round(v[k], 4) for v in out.values() if not v["exc"].startswith("damaged"))[-6:])
        print(s, "median s", round(float(np.median([v["s"] for v in out.values()])), 3))
