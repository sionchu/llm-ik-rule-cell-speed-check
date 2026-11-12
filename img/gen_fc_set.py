"""FC (fulfilment-centre) outbound-check image set, same Isaac cell (doc 28 sec. 8, scope 1: label / damage / spec / packing).
Sets: fc_stream (200, ~5% faults, oversampled vs real 0.1-0.5%) and fc_hard (100, ~80% faults + unseen forms:
crushed corner, oil stain, Korean/orange fragile sticker, wrong-order label with unreadable barcode).
Run: python img/gen_fc_set.py -> img/sets/fc_*.jsonl + img/tex/fc_*_top.png"""
import json, os, random, sys, math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import barcode
from barcode.writer import ImageWriter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_image_set as g

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = g.W, g.H
CAMPS = ["C01", "C02", "C04", "C07", "C11", "C15"]
SKUS = [("Ceramic mug 350ml", 0.38, True), ("Glass storage jar 1L", 0.62, True), ("Wine glass set (2)", 0.55, True),
        ("Cotton T-shirt M", 0.21, False), ("Running socks 3-pack", 0.15, False), ("Phone case", 0.08, False),
        ("Shampoo 500ml", 0.56, False), ("Instant noodles 5-pack", 0.62, False), ("Paperback book", 0.34, False),
        ("Coffee beans 1kg", 1.05, False), ("Ceramic plate 26cm", 0.71, True), ("Desk lamp", 1.20, False)]


def latent(i, r, mode):
    hard = mode == "fc_hard"
    n = r.choice([1, 1, 2, 3]); items = []
    for s in r.sample(SKUS, n):
        items.append(dict(name=s[0], qty=r.choice([1, 1, 2]), unit_kg=s[1], fragile=s[2]))
    box_kg = 0.25
    exp = round(sum(it["qty"] * it["unit_kg"] for it in items) + box_kg, 2)
    fragile = any(it["fragile"] for it in items)
    order = dict(order_no=f"{r.randint(10**11, 10**12 - 1)}", camp=r.choice(CAMPS), items=items, expected_kg=exp, fragile=fragile)
    z = dict(id=f"{mode}_{i:04d}", order=order, label_order=order["order_no"], weight=round(exp * r.uniform(0.98, 1.02), 2),
             dims=[r.randint(22, 50), r.randint(18, 40), r.randint(8, 30)], barcode="ok", degrade="none", exc="none",
             sticker=("red" if fragile else "none"), form="canonical", action="OK")
    if fragile and r.random() < (0.5 if hard else 0.15): z["sticker"] = "orange_ko"          # unseen form: Korean text, orange
    if r.random() < (0.35 if hard else 0.12): z["degrade"] = r.choice(["blur", "glare", "crease"])
    e = r.random()
    cut = ([(0.16, "label"), (0.28, "wrong_label"), (0.38, "damaged_wet"), (0.46, "crushed"), (0.54, "oil"), (0.66, "weight"), (0.80, "no_sticker")]
           if hard else [(0.012, "label"), (0.016, "wrong_label"), (0.024, "damaged_wet"), (0.028, "damaged_torn"), (0.038, "weight"), (0.05, "no_sticker")])
    for c, nm in cut:
        if e < c: z["exc"] = nm; break
    x = z["exc"]
    if x == "label":
        if r.random() < 0.3: z["degrade"] = "unreadable"; z["barcode"] = "missing"
        else: z["barcode"] = r.choice(["smudged", "torn", "missing"])
        z["action"] = "RELABEL"
    elif x == "wrong_label":
        z["label_order"] = f"{r.randint(10**11, 10**12 - 1)}"; z["action"] = "MANUAL"
        if hard and r.random() < 0.5: z["barcode"] = r.choice(["smudged", "torn"])        # only the printed number shows the mismatch
    elif x in ("damaged_wet", "damaged_torn", "crushed", "oil"):
        z["action"] = "DAMAGED"
    elif x == "weight":
        f = r.choice([r.uniform(0.6, 0.9), r.uniform(1.1, 1.6)]); z["weight"] = round(exp * f, 2); z["action"] = "SPEC_OUT"
    elif x == "no_sticker":
        if not fragile:                                      # make the order fragile
            it = dict(name="Glass storage jar 1L", qty=1, unit_kg=0.62, fragile=True); items.append(it)
            order["fragile"] = True; order["expected_kg"] = round(exp + 0.62, 2); z["weight"] = round(order["expected_kg"] * r.uniform(0.98, 1.02), 2)
        z["sticker"] = "none"; z["action"] = "PACK_UNFIT"
    z["exc_render"] = "damaged_wet" if x == "damaged_wet" else ("damaged_torn" if x == "damaged_torn" else "none")
    return z


def render_label(z, r):
    im = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(im)
    dr.rectangle([4, 4, W - 5, H - 5], outline="black", width=4)
    dr.text((24, 18), "FC SHIP LABEL", font=g.font(30, True), fill="black")
    dr.text((W - 300, 18), f"CAMP {z['order']['camp']}", font=g.font(40, True), fill="black")
    dr.line([16, 70, W - 16, 70], fill="black", width=3)
    dr.text((24, 86), f"ORDER {z['label_order']}", font=g.font(40, True), fill="black")
    dr.text((24, 146), f"{sum(it['qty'] for it in z['order']['items'])} item(s)   wave {r.randint(1, 9)}   route {r.randint(10, 99)}", font=g.font(30), fill="black")
    bc = barcode.get("code128", "ORD" + z["label_order"], writer=ImageWriter()).render(
        dict(module_height=18, module_width=0.42, quiet_zone=4, font_size=7, text_distance=3, dpi=300)).convert("RGB")
    bw = W - 80; bh = int(bc.height * bw / bc.width); bc = bc.resize((bw, min(bh, 260))); by = H - bc.height - 18
    im.paste(bc, (40, by)); dr = ImageDraw.Draw(im)
    if z["barcode"] == "smudged":
        for _ in range(9):
            x0 = r.randint(40, W - 160); dr.ellipse([x0, by + r.randint(0, 80), x0 + r.randint(80, 200), by + r.randint(120, 220)], fill=(40, 40, 40))
    elif z["barcode"] == "missing":
        dr.rectangle([30, by - 4, W - 30, H - 10], fill="white"); dr.text((60, by + 60), "(barcode label peeled off)", font=g.font(28), fill=(120, 120, 120))
    elif z["barcode"] == "torn":
        pts = [(40, by)] + [(40 + k * 60, by + r.randint(40, 200)) for k in range(16)] + [(W - 40, H - 10), (40, H - 10)]
        dr.polygon(pts, fill=(176, 132, 84))
    if z["degrade"] == "blur": im = im.filter(ImageFilter.GaussianBlur(2.2))
    elif z["degrade"] == "glare":
        gl = Image.new("L", (W, H), 0); gd = ImageDraw.Draw(gl); cx, cy = r.randint(250, 750), r.randint(150, 450)
        for k in range(40, 0, -1): gd.ellipse([cx - 9 * k, cy - 5 * k, cx + 9 * k, cy + 5 * k], fill=int(255 * (1 - k / 40) ** 0.6))
        im = Image.composite(Image.new("RGB", (W, H), "white"), im, gl)
    elif z["degrade"] == "crease":
        dr = ImageDraw.Draw(im)
        for _ in range(3):
            x = r.randint(100, 900); dr.line([x, 0, x + r.randint(-120, 120), H], fill=(150, 150, 150), width=r.randint(6, 14))
        im = im.rotate(r.uniform(-4, 4), fillcolor="white")
    elif z["degrade"] == "unreadable":
        im = im.filter(ImageFilter.GaussianBlur(9)); dr = ImageDraw.Draw(im); dr.rectangle([60, 80, W - 60, 300], fill=(230, 230, 230))
    return im


def sticker(kind, PX):
    w, h = int(9 * PX), int(5 * PX); s = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(s)
    if kind == "red":
        d.rectangle([0, 0, w - 1, h - 1], fill=(200, 20, 30)); d.text((int(0.6 * PX), int(1.2 * PX)), "FRAGILE", font=g.font(int(1.9 * PX), True), fill="white")
    else:
        d.rectangle([0, 0, w - 1, h - 1], fill=(250, 170, 40)); d.text((int(0.5 * PX), int(1.0 * PX)), "취급주의", font=g.font(int(2.2 * PX), True), fill="black")
    return s


def render_top(z, lab, r):
    zz = dict(z, exc=z["exc_render"]); im = g.render_top(zz, lab, r); TW, TH = im.size; PX = 40; S = min(TW, TH); dr = ImageDraw.Draw(im)
    if z["exc"] == "crushed":                     # unseen damage: dented corner, grey creases + shadow (not brown)
        cx, cy = r.choice([(0, 0), (TW, 0), (0, TH), (TW, TH)]); s = int(S * 0.45)    # v2: darker and larger (v1 washed out under the cell light)
        dr.polygon([(cx, cy), (abs(cx - s), cy), (cx, abs(cy - s))], fill=(85, 75, 68))
        for k in range(7): dr.line([abs(cx - s * k / 7), cy, cx, abs(cy - s * (7 - k) / 7)], fill=(45, 40, 36), width=10)
    elif z["exc"] == "oil":                       # unseen damage: dark grey translucent stain
        ov = Image.new("L", im.size, 0); od = ImageDraw.Draw(ov)
        for _ in range(5):
            cx, cy, s = r.randint(S // 5, TW - S // 5), r.randint(S // 5, TH - S // 5), r.randint(S // 10, S // 5)
            od.ellipse([cx - s, cy - int(s * 0.7), cx + s, cy + int(s * 0.7)], fill=150)
        im = Image.composite(Image.new("RGB", im.size, (70, 70, 72)), im, ov.filter(ImageFilter.GaussianBlur(12)))
    if z["sticker"] != "none":
        # v2: alpha-masked rotation (v1 pasted cardboard-coloured corners) and never over the label (v1 could cover it -> "obscured" on OK cartons)
        st = sticker(z["sticker"], PX).convert("RGBA").rotate(r.uniform(-20, 20), expand=True)
        a = np.asarray(im).astype(int); wm = (a.min(axis=2) > 225)
        ys, xs = np.nonzero(wm); lb = (xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else (0, 0, -1, -1)
        best = None
        for _ in range(200):
            x, y = r.randint(0, max(0, TW - st.width)), r.randint(0, max(0, TH - st.height))
            ov = max(0, min(x + st.width, lb[2]) - max(x, lb[0])) * max(0, min(y + st.height, lb[3]) - max(y, lb[1]))
            if best is None or ov < best[0]: best = (ov, x, y)
            if ov == 0: break
        z["sticker_label_overlap_px"] = int(best[0])
        im.paste(st, (best[1], best[2]), st)
    return im


def main():
    from collections import Counter
    for mode, seed, n in (("fc_stream", 21, 200), ("fc_hard", 22, 100)):
        r = random.Random(seed); rows = []
        for i in range(n):
            z = latent(i, r, mode); rr = random.Random(f"{seed}-{i}"); lab = render_label(z, rr); top = render_top(z, lab, rr)
            top.save(os.path.join(HERE, "tex", f"{z['id']}_top.png")); rows.append(z)
        with open(os.path.join(HERE, "sets", f"{mode}.jsonl"), "w", encoding="utf-8") as f:
            for z in rows: f.write(json.dumps(z, ensure_ascii=False) + "\n")
        print(mode, n, Counter(z["action"] for z in rows), Counter(z["exc"] for z in rows), Counter(z["sticker"] for z in rows))


if __name__ == "__main__":
    main()
