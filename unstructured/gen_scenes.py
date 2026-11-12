"""Generate unstructured scenes + top-view images with numbered grasp points. python gen_scenes.py N seed"""
import json, math, os, random, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from common_u import *
HERE = os.path.dirname(os.path.abspath(__file__))

def scene(i, r):
    L = r.uniform(0.20, 0.50); W = r.uniform(0.15, min(L, 0.40)); H = r.uniform(0.08, 0.35)
    b = dict(id=f"u_{i:03d}", L=L, W=W, H=H, mass=round(r.uniform(1, 20), 1), yaw=r.uniform(-math.pi / 2, math.pi / 2),
             x=r.uniform(-0.15, 0.15), y=BELT_Y + r.uniform(-0.10, 0.10), dest=r.randrange(15), damage=[], neighbor=None)
    ext = 0.5 * (abs(math.sin(b["yaw"])) * L + abs(math.cos(b["yaw"])) * W)          # half extent across the belt
    b["y"] = float(np.clip(b["y"], BELT_Y - BELT_HALF + ext + 0.01, BELT_Y + BELT_HALF - ext - 0.01))
    k = r.random()
    kind = "none" if k < 0.35 else "torn" if k < 0.65 else "wet" if k < 0.90 else "both"
    def spot(near_center):
        if near_center: return r.uniform(-0.12, 0.12) * L, r.uniform(-0.12, 0.12) * W
        return r.uniform(-0.4, 0.4) * L, r.uniform(-0.4, 0.4) * W
    if kind in ("torn", "both"):
        x, y = spot(r.random() < 0.5); b["damage"].append(dict(kind="torn", x=x, y=y, r=r.uniform(0.035, 0.08)))
    if kind in ("wet", "both"):
        for _ in range(r.randint(1, 3)):
            x, y = spot(r.random() < 0.4); b["damage"].append(dict(kind="wet", x=x, y=y, r=r.uniform(0.03, 0.06)))
    b["label"] = dict(x=r.uniform(-0.25, 0.25) * L, y=r.uniform(-0.2, 0.2) * W)
    if r.random() < 0.5:   # neighbour box next to it on the belt (taller ones block a low transfer)
        side = r.choice([-1, 1]); nl = r.uniform(0.2, 0.4)
        b["neighbor"] = dict(x=b["x"] + side * (0.5 * abs(math.cos(b["yaw"])) * L + 0.5 * abs(math.sin(b["yaw"])) * W + nl / 2 + r.uniform(0.02, 0.05)),
                             y=b["y"], L=nl, W=r.uniform(0.2, 0.4), H=r.uniform(0.1, 0.45))
    b["kind"] = kind
    return b

def draw(b, path):
    S = 1400; PX = 2200                       # px per m, centred on the box
    im = Image.new("RGB", (S, S), (150, 150, 155)); d = ImageDraw.Draw(im)
    def P(wx, wy): return (S / 2 + (wx - b["x"]) * PX, S / 2 - (wy - b["y"]) * PX)
    def poly_box(cx, cy, L, W, yaw):
        c, s = math.cos(yaw), math.sin(yaw)
        return [P(cx + c * u - s * v, cy + s * u + c * v) for u, v in ((-L / 2, -W / 2), (L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2))]
    if b["neighbor"]:
        n = b["neighbor"]; d.polygon(poly_box(n["x"], n["y"], n["L"], n["W"], 0), fill=(176, 140, 95), outline=(90, 70, 50))
        cx, cy = P(n["x"], n["y"]); d.text((cx - 60, cy), f"other box h={n['H']*100:.0f}cm", fill="black")
    d.polygon(poly_box(b["x"], b["y"], b["L"], b["W"], b["yaw"]), fill=(205, 165, 115), outline=(80, 60, 40))
    d.polygon([tuple(p) for p in [P(*box_to_world(b, q)) for q in ((-b["L"] / 2, -0.025), (b["L"] / 2, -0.025), (b["L"] / 2, 0.025), (-b["L"] / 2, 0.025))]], fill=(222, 205, 170))  # tape
    lb = b["label"]
    d.polygon([P(*box_to_world(b, (lb["x"] + u, lb["y"] + v))) for u, v in ((-0.07, -0.045), (0.07, -0.045), (0.07, 0.045), (-0.07, 0.045))], fill=(245, 245, 245), outline=(30, 30, 30))
    for dm in b["damage"]:
        cx, cy = P(*box_to_world(b, (dm["x"], dm["y"]))); rr = dm["r"] * PX
        if dm["kind"] == "torn":
            pts = [(cx + math.cos(a) * rr * (0.75 + 0.25 * math.sin(5 * a)), cy + math.sin(a) * rr * (0.75 + 0.25 * math.sin(5 * a))) for a in np.linspace(0, 2 * math.pi, 18)]
            d.polygon(pts, fill=(120, 106, 96)); d.rectangle([cx - rr / 4, cy - rr / 5, cx + rr / 5, cy + rr / 4], fill=(232, 232, 240))
        else:
            d.ellipse([cx - rr, cy - rr / 1.2, cx + rr, cy + rr / 1.2], fill=(160, 120, 82))
    try: f = ImageFont.truetype("arial.ttf", 34)
    except Exception: f = None
    for k, g in enumerate(grasp_points(b)):
        cx, cy = P(*box_to_world(b, g)); rr = CUP_R * PX
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(0, 90, 255), width=4); d.text((cx - 9, cy - 18), str(k), fill=(0, 60, 220), font=f)
    im.save(path, quality=90)

if __name__ == "__main__":
    n, seed = int(sys.argv[1]), int(sys.argv[2]); r = random.Random(seed)
    os.makedirs(os.path.join(HERE, "img"), exist_ok=True)
    with open(os.path.join(HERE, "scenes.jsonl"), "w") as f:
        for i in range(n):
            b = scene(i, r); draw(b, os.path.join(HERE, "img", f"{b['id']}.jpg")); f.write(json.dumps(b) + "\n")
    print("ok", n)
