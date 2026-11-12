"""Image parcel set for the Isaac sorting cell (2026-11-11).
Latent state per parcel -> ground-truth action + a label texture (PNG) and a top-face texture with damage/hazmat marks.
Two sets: 'stream' (realistic mix: most parcels have a readable barcode) and 'hard' (exceptions + unseen address forms).
Degradations are physical (blur, glare, crease, smudge over barcode) so failures come from real decoding/OCR, not flags.
Run on Windows venv: python gen_image_set.py  -> sets/{stream,hard}.jsonl + tex/*.png"""
import json, os, random, sys, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import barcode
from barcode.writer import ImageWriter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gen_parcels import CHUTES, PLAN, PLACES, HANGUL, OLD_ROMAN, LANDMARK, STREETS, NAMES

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = r"C:\Windows\Fonts\malgun.ttf"; FONTB = r"C:\Windows\Fonts\malgunbd.ttf"
W, H = 1000, 640                          # label px (prints at ~100 x 64 mm)
SORTCODE = {c: f"{i+1:02d}" for i, c in enumerate(CHUTES)}   # barcode payload = tracking + 2-digit sort code


def font(sz, bold=False):
    return ImageFont.truetype(FONTB if bold else FONT, sz)


def code_for(ch, r):
    return r.choice(PLAN[ch]) + f"{r.randint(0, 999):03d}"


def latent(i, r, mode):
    ch = r.choice(CHUTES); city, dists = PLACES[ch]; dist = r.choice(dists)
    code = code_for(ch, r); name = r.choice(NAMES); street = f"{r.randint(1, 600)} {r.choice(STREETS)}"
    z = dict(id=f"{mode}_{i:04d}", chute=ch, name=name, weight=round(r.uniform(0.3, 18), 1),
             dims=[r.randint(25, 60), r.randint(20, 45), r.randint(10, 35)], form="canonical", show_code=True,
             barcode="ok", degrade="none", exc="none", action=ch)
    hard = mode == "hard"
    # address form
    u = r.random()
    if u < (0.45 if hard else 0.05):
        z["form"] = r.choice(["hangul", "old_roman", "landmark", "district_only"])
    if z["form"] == "canonical":
        z["lines"] = [street, f"{dist}, {city}", code]
    elif z["form"] == "district_only":
        z["lines"] = [street, dist]; z["show_code"] = False
    elif z["form"] == "hangul":
        z["lines"] = [HANGUL[ch], street.split()[0] + " " + street.split()[1]]; z["show_code"] = False
    elif z["form"] == "old_roman":
        z["lines"] = [street, OLD_ROMAN[ch]]; z["show_code"] = False
    else:
        z["lines"] = [LANDMARK[ch]]; z["show_code"] = False
    # barcode state: most stream parcels read fine
    b = r.random()
    if b < (0.70 if hard else 0.06):
        z["barcode"] = r.choice(["smudged", "missing", "torn"])
    # label degradation
    d = r.random()
    if d < (0.5 if hard else 0.15):
        z["degrade"] = r.choice(["blur", "glare", "crease"])
    # exceptions
    e = r.random()
    if hard:
        cut = [(0.10, "unreadable"), (0.22, "damaged_wet"), (0.32, "damaged_torn"), (0.42, "hazmat"), (0.50, "overweight"), (0.56, "conflict")]
    else:
        cut = [(0.01, "unreadable"), (0.025, "damaged_wet"), (0.035, "damaged_torn"), (0.045, "hazmat"), (0.06, "overweight")]
    for c, name_ in cut:
        if e < c:
            z["exc"] = name_; break
    if z["exc"] == "unreadable":
        z["degrade"] = "unreadable"; z["barcode"] = "missing"; z["action"] = "RESCAN"
    elif z["exc"].startswith("damaged"):
        z["action"] = "REJECT"
    elif z["exc"] == "hazmat":
        z["action"] = "MANUAL"
    elif z["exc"] == "overweight":
        z["weight"] = round(r.uniform(31, 45), 1); z["action"] = "MANUAL"
    elif z["exc"] == "conflict" and z["form"] == "canonical":
        other = r.choice([c for c in CHUTES if PLACES[c][0] != city])
        z["lines"][2] = code_for(other, r); z["barcode"] = r.choice(["smudged", "missing"]); z["action"] = "MANUAL"
    else:
        if z["exc"] == "conflict": z["exc"] = "none"
    # address only on label with no barcode and ambiguous district -> unknowable -> MANUAL
    amb = z["form"] == "district_only" and sum(z["lines"][1] in PLACES[c][1] for c in CHUTES) > 1
    if amb and z["barcode"] != "ok" and z["action"] in CHUTES:
        z["action"] = "MANUAL"; z["exc"] = "ambiguous"
    z["tracking"] = f"KR{r.randint(10**9, 10**10 - 1)}"
    return z


def draw_barcode(z):
    data = z["tracking"] + SORTCODE[z["chute"]]
    img = barcode.get("code128", data, writer=ImageWriter()).render(dict(module_height=18, module_width=0.42, quiet_zone=4,
                                                                         font_size=7, text_distance=3, dpi=300))
    return img.convert("RGB")


def render_label(z, r):
    im = Image.new("RGB", (W, H), "white"); dr = ImageDraw.Draw(im)
    dr.rectangle([4, 4, W - 5, H - 5], outline="black", width=4)
    dr.text((24, 18), "PARCEL EXPRESS", font=font(30, True), fill="black")
    dr.text((W - 330, 22), f"{z['weight']} kg  {z['dims'][0]}x{z['dims'][1]}x{z['dims'][2]}", font=font(24), fill="black")
    dr.line([16, 64, W - 16, 64], fill="black", width=3)
    dr.text((24, 78), "TO:", font=font(30, True), fill="black")
    y = 80
    dr.text((90, y), z["name"], font=font(36, True), fill="black"); y += 52
    for ln in z["lines"]:
        dr.text((90, y), ln, font=font(40, True), fill="black"); y += 54
    if z["exc"] == "hazmat":
        # diamond + UN number
        cx, cy, s = W - 120, 190, 80
        dr.polygon([(cx, cy - s), (cx + s, cy), (cx, cy + s), (cx - s, cy)], outline="red", width=8)
        un = r.choice(["UN3480", "UN1845", "UN1993"])
        dr.text((cx - 52, cy - 18), un, font=font(30, True), fill="black"); z["un"] = un
    bc = draw_barcode(z)
    bw = W - 80; bh = int(bc.height * bw / bc.width)
    bc = bc.resize((bw, min(bh, 230)))
    by = H - bc.height - 18
    im.paste(bc, (40, by))
    dr = ImageDraw.Draw(im)
    if z["barcode"] == "smudged":
        for _ in range(9):
            x0 = r.randint(40, W - 160); dr.ellipse([x0, by + r.randint(0, 80), x0 + r.randint(80, 200), by + r.randint(120, 220)], fill=(40, 40, 40))
    elif z["barcode"] == "missing":
        dr.rectangle([30, by - 4, W - 30, H - 10], fill="white"); dr.text((60, by + 60), "(barcode label peeled off)", font=font(28), fill=(120, 120, 120))
    elif z["barcode"] == "torn":
        pts = [(40, by)] + [(40 + k * 60, by + r.randint(40, 200)) for k in range(16)] + [(W - 40, H - 10), (40, H - 10)]
        dr.polygon(pts, fill=(176, 132, 84))
    if z["degrade"] == "blur":
        im = im.filter(ImageFilter.GaussianBlur(2.2))
    elif z["degrade"] == "glare":
        gl = Image.new("L", (W, H), 0); g = ImageDraw.Draw(gl)
        cx, cy = r.randint(250, 750), r.randint(150, 450)
        for k in range(40, 0, -1):
            g.ellipse([cx - 9 * k, cy - 5 * k, cx + 9 * k, cy + 5 * k], fill=int(255 * (1 - k / 40) ** 0.6))
        im = Image.composite(Image.new("RGB", (W, H), "white"), im, gl)
    elif z["degrade"] == "crease":
        dr = ImageDraw.Draw(im)
        for _ in range(3):
            x = r.randint(100, 900); dr.line([x, 0, x + r.randint(-120, 120), H], fill=(150, 150, 150), width=r.randint(6, 14))
        im = im.rotate(r.uniform(-4, 4), fillcolor="white")
    elif z["degrade"] == "unreadable":
        im = im.filter(ImageFilter.GaussianBlur(9))
        dr = ImageDraw.Draw(im); dr.rectangle([60, 120, W - 60, 380], fill=(230, 230, 230))
    return im


def render_top(z, label, r):
    """Top face of the carton with the label; texture keeps the carton's real aspect (L x W) so the label is not stretched.
    Damage marks drawn on the cardboard."""
    L, Wd = z["dims"][0], z["dims"][1]
    PX = 40                                   # px per cm on the carton face (0.25 mm/px; v2 used 20 and the barcode bars blurred)
    TW, TH = int(L * PX), int(Wd * PX)
    im = Image.new("RGB", (TW, TH), (186, 142, 92)); dr = ImageDraw.Draw(im)
    for _ in range(int(TH / 12)):
        y = r.randint(0, TH); dr.line([0, y, TW, y + r.randint(-6, 6)], fill=(178 + r.randint(-6, 6), 136, 88), width=2)
    dr.rectangle([0, TH // 2 - int(1.25 * PX), TW, TH // 2 + int(1.25 * PX)], fill=(205, 190, 160))   # packing tape
    lw = min(int(15 * PX), int(TW * 0.8)); lh = int(lw * H / W)                # label ~15 x 9.6 cm, smaller on small cartons
    if lh > TH * 0.8: lh = int(TH * 0.8); lw = int(lh * W / H)
    lab = label.resize((lw, lh), Image.LANCZOS).rotate(r.uniform(-12, 12), expand=True, fillcolor=(186, 142, 92))
    ox, oy = r.randint(0, max(0, TW - lab.width)), r.randint(0, max(0, TH - lab.height))
    im.paste(lab, (ox, oy))
    dr = ImageDraw.Draw(im); S = min(TW, TH)
    if z["exc"] == "damaged_wet":
        for _ in range(14):
            cx, cy, s = r.randint(0, TW), r.randint(0, TH), r.randint(S // 12, S // 5)
            dr.ellipse([cx - s, cy - s // 1.3, cx + s, cy + s // 1.3], fill=(96, 66, 40))
    elif z["exc"] == "damaged_torn":
        cx, cy = r.randint(S // 6, TW - S // 6), r.randint(S // 6, TH - S // 6)
        pts = [(cx + math.cos(a) * r.randint(S // 8, S // 4), cy + math.sin(a) * r.randint(S // 8, S // 4)) for a in [k * 0.45 for k in range(14)]]
        dr.polygon(pts, fill=(40, 30, 22))
        for _ in range(5):
            dr.rectangle([cx - S // 16 + r.randint(-int(1.5 * PX), int(1.5 * PX)), cy - S // 30 + r.randint(-int(1.5 * PX), int(1.5 * PX)), cx + S // 30, cy + S // 25], fill=(230, 230, 240))
    return im


def main():
    os.makedirs(os.path.join(HERE, "tex"), exist_ok=True); os.makedirs(os.path.join(HERE, "sets"), exist_ok=True)
    for mode, seed, n in (("stream", 11, int(os.environ.get("NSTREAM", 200))), ("hard", 12, int(os.environ.get("NHARD", 100)))):
        r = random.Random(seed); rows = []
        for i in range(n):
            z = latent(i, r, mode); rr = random.Random(f"{seed}-{i}"); lab = render_label(z, rr); top = render_top(z, lab, rr)   # render rng separate from latent rng
            lab.save(os.path.join(HERE, "tex", f"{z['id']}_label.png")); top.save(os.path.join(HERE, "tex", f"{z['id']}_top.png"))
            rows.append(z)
        with open(os.path.join(HERE, "sets", f"{mode}.jsonl"), "w", encoding="utf-8") as f:
            for z in rows: f.write(json.dumps(z, ensure_ascii=False) + "\n")
        from collections import Counter
        print(mode, n, Counter(z["action"] in CHUTES for z in rows), Counter(z["exc"] for z in rows), Counter(z["barcode"] for z in rows))


if __name__ == "__main__":
    main()
