"""LinkedIn clip (English, fast cut): same parcel, three deciders side by side — Rule vs Claude Opus 5.5 vs Claude Fable 5.2.
Each panel's robot acts on its own decision after its own measured decision time (Isaac front view, sort_cell.py --video).
Motion recipes borrowed from video-shotcraft / OpenMontage (flash cuts, digit rolls, spring text, stamp reveals), implemented in PIL + ffmpeg.
Output: results/FC_outbound_check_linkedin_EN.mp4 (1920x1080, 30 fps)"""
import json, math, os, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio_ffmpeg
os.environ["ROI"] = "1"
R = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(R, "img"))
import decide_llm_image as D

W, H, FPS, SRC = 1920, 1080, 30, 24
SPEED = 2.0                                   # sim seconds per video second in the triptych
def F(sz, w="b"): return ImageFont.truetype({"b": r"C:\Windows\Fonts\segoeuib.ttf", "r": r"C:\Windows\Fonts\segoeui.ttf", "l": r"C:\Windows\Fonts\segoeuil.ttf"}[w], sz)
NAVY, INK, MUTE, WHITE = (13, 20, 36), (24, 28, 36), (120, 128, 140), (255, 255, 255)
GOOD, BAD, ACC, API, AMB = (30, 170, 95), (226, 64, 52), (52, 120, 246), (245, 160, 40), (255, 205, 70)
VERB = {"OK": "OK - ship", "DAMAGED": "DAMAGED - reject", "RELABEL": "RELABEL", "SPEC_OUT": "WEIGHT OFF", "PACK_UNFIT": "REPACK", "MANUAL": "WRONG ORDER"}
meta = json.load(open(os.path.join(R, "results", "video", "meta2.json")))
cost = json.load(open(os.path.join(R, "results", "cost10k.json")))
M3 = [("rule", "RULE", "barcode + weight + color", "pred_rule_fc_{s}.jsonl"),
      ("opus", "CLAUDE OPUS 5.5", "LLM, image + order", "pred_claude_claude-opus-5-5-low_roi_{s}.jsonl"),
      ("fable", "CLAUDE FABLE 5.2", "LLM, image + order", "pred_claude_claude-fable-5-2-low_roi_{s}.jsonl")]

def pred(fn, sid):
    s = sid.rsplit("_", 1)[0]
    for l in open(os.path.join(R, "img", fn.format(s=s)), encoding="utf-8"):
        j = json.loads(l)
        if j["id"] == sid: return j["pred"], j["latency_s"], j["gold"]

out_path = os.path.join(R, "results", "FC_outbound_check_linkedin_EN.mp4")
ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                       "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path],
                      stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
N = [0]
def emit(im, n=1):
    b = im.convert("RGB").tobytes()
    for _ in range(n): ff.stdin.write(b); N[0] += 1

# ---- motion helpers (spring / ease / digit roll)
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def ease_out(t): t = clamp(t); return 1 - (1 - t) ** 3
def back(t):  # ease-out-back (overshoot), spring-like pop
    t = clamp(t); c1 = 1.70158; c3 = c1 + 1; return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
def text(d, xy, s, f, fill=INK, anchor="la"): d.text(xy, s, font=f, fill=fill, anchor=anchor)
def pop_text(im, xy, s, f, fill, t, anchor="la"):
    """word pops in: scale 0.6->1 with overshoot + fade, rendered on its own layer"""
    if t <= 0: return
    k = 0.6 + 0.4 * back(t); a = int(255 * ease_out(t * 1.6))
    L = Image.new("RGBA", im.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
    fs = F(max(8, int(f.size * k)), "b" if "segoeuib" in f.path else "r"); dl.text(xy, s, font=fs, fill=fill + (a,), anchor=anchor)
    im.alpha_composite(L)
def flash(prev, n=3):
    for k in range(n):
        a = [0.85, 0.5, 0.2][k] if k < 3 else 0
        emit(Image.blend(prev.convert("RGB"), Image.new("RGB", (W, H), WHITE), a))

# ---------- scene A: hook (2.4 s)
def hook():
    n = int(2.4 * FPS); last = None
    for i in range(n):
        t = i / FPS; im = Image.new("RGBA", (W, H), NAVY + (255,)); d = ImageDraw.Draw(im)
        pop_text(im, (W // 2, 380), "Is an LLM too slow", F(110), WHITE, (t - 0.0) / 0.35, "ma")
        pop_text(im, (W // 2, 520), "for a robot parcel line?", F(110), AMB, (t - 0.35) / 0.35, "ma")
        pop_text(im, (W // 2, 720), "We measured it.  Isaac Sim  ·  same parcels  ·  same camera", F(40, "r"), (170, 180, 200), (t - 0.9) / 0.3, "ma")
        emit(im); last = im
    flash(last)

# ---------- scene B/C: triptych
PX0, PW, PG, PTOP, PH_IMG = 380, 500, 20, 150, 620
CROP = (520, 40, 1340, 1060)                   # region of the 1920x1080 front render around robot / tote / induct
INS = {}
def inset(sid):
    if sid not in INS:
        w = tempfile.mkdtemp(); D.to_jpeg(os.path.join(R, "cam", f"{sid}.png"), os.path.join(w, "view.jpg"))
        v = Image.open(os.path.join(w, "view.jpg")).convert("RGB"); v.thumbnail((320, 300)); INS[sid] = v
    return INS[sid]
_cache = {}
def src(key, i):
    m = meta[key]; i = int(clamp(i, 0, m["frames"] - 1)); p = os.path.join(R, "results", "video", key, f"{i:04d}.png")
    if p not in _cache:
        if len(_cache) > 400: _cache.clear()
        _cache[p] = Image.open(p).convert("RGB").crop(CROP).resize((PW, PH_IMG), Image.LANCZOS)
    return _cache[p]

def triptych(sid, header, truth, hold_end=1.4, stamp=True):
    rows = []
    for mk, name, sub, fn in M3:
        p, lat, g = pred(fn, sid); key = f"{sid}_{'induct' if p == 'OK' else 'tote'}"; rows.append((mk, name, sub, p, lat, p == g, key))
    A = meta[rows[0][6]]["arrive_frames"] / SRC
    s_end = max(A + r[4] + (meta[r[6]]["frames"] - meta[r[6]]["arrive_frames"]) / SRC for r in rows)
    n_run = int(s_end / SPEED * FPS) + 1; n_hold = int(hold_end * FPS); last = None
    for i in range(n_run + n_hold):
        tv = i / FPS; s = min(tv * SPEED, s_end); th = max(0.0, (i - n_run) / FPS)
        im = Image.new("RGBA", (W, H), (244, 246, 250, 255)); d = ImageDraw.Draw(im)
        # header
        pop_text(im, (40, 34), header, F(54), INK, tv / 0.3)
        text(d, (40, 104), truth, F(28, "r"), MUTE)
        text(d, (W - 40, 50), f"{SPEED:.0f}x speed", F(26, "r"), MUTE, "ra")
        # left: pick camera
        v = inset(sid); d.rounded_rectangle([30, PTOP, 30 + 330, PTOP + v.height + 70], 14, fill=WHITE)
        im.paste(v, (35, PTOP + 5)); text(d, (40, PTOP + v.height + 18), "Pick camera (top view)", F(24), INK)
        text(d, (40, PTOP + v.height + 46), "input to every decider", F(20, "r"), MUTE)
        text(d, (40, 760), "Robot cycle", F(26), INK); text(d, (40, 794), "4.5 - 6.1 s", F(40), AMB[:3] if False else (200, 140, 20))
        text(d, (40, 860), "Human video coding", F(26), INK); text(d, (40, 894), "~15 s", F(40), MUTE); text(d, (40, 944), "(industry figure)", F(20, "r"), MUTE)
        for k, (mk, name, sub, p, lat, ok, key) in enumerate(rows):
            x = PX0 + k * (PW + PG); m = meta[key]
            if s < A: fi = s * SRC
            elif s < A + lat: fi = m["arrive_frames"] - 1
            else: fi = m["arrive_frames"] + (s - A - lat) * SRC
            d.rounded_rectangle([x - 4, PTOP - 4, x + PW + 4, PTOP + PH_IMG + 214], 16, fill=WHITE)
            im.paste(src(key, fi), (x, PTOP))
            # thinking overlay while deciding
            yb = PTOP + PH_IMG
            text(d, (x + 18, yb + 16), name, F(34), INK); text(d, (x + 18, yb + 58), sub, F(22, "r"), MUTE)
            el = clamp(s - A, 0, lat)
            decided = s >= A + lat
            col = (GOOD if ok else BAD) if decided else ACC
            text(d, (x + PW - 18, yb + 14), f"{el:4.1f} s", F(46), col, "ra")
            bw = PW - 36; d.rounded_rectangle([x + 18, yb + 104, x + 18 + bw, yb + 118], 7, fill=(228, 232, 240))
            d.rounded_rectangle([x + 18, yb + 104, x + 18 + max(14, bw * min(el, 7.0) / 7.0), yb + 118], 7, fill=col)
            if s >= A and not decided:
                dots = "." * (1 + int(tv * 4) % 3); text(d, (x + 18, yb + 140), "deciding" + dots, F(34, "r"), ACC)
            if decided:
                pop_text(im, (x + 18, yb + 132), VERB[p], F(40), col, (s - A - lat) / SPEED / 0.25)
            if stamp and th > 0:
                lab, c = ("CAUGHT", GOOD) if ok else ("MISSED", BAD)
                t2 = clamp(th / 0.3); k2 = 2.2 - 1.2 * back(t2)
                L = Image.new("RGBA", (420, 150), (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
                dl.rounded_rectangle([6, 6, 414, 144], 18, outline=c + (255,), width=10); dl.text((210, 75), lab, font=F(84), fill=c + (255,), anchor="mm")
                L = L.rotate(-8, expand=True, resample=Image.BICUBIC); L = L.resize((max(1, int(L.width * k2 * 0.8)), max(1, int(L.height * k2 * 0.8))))
                a = L.split()[3].point(lambda v: int(v * ease_out(t2 * 1.5))); L.putalpha(a)
                im.alpha_composite(L, (int(x + PW / 2 - L.width / 2), int(PTOP + PH_IMG / 2 - L.height / 2)))
        emit(im); last = im
    return last

# ---------- stat cards (2.9 s each, spring bars + digit rolls)
def card_frame(title, sub, t):
    im = Image.new("RGBA", (W, H), (250, 251, 253, 255)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, int(W * ease_out(t / 0.4)), 10], fill=ACC)
    pop_text(im, (110, 90), title, F(68), INK, t / 0.3); text(d, (112, 190), sub, F(30, "r"), MUTE)
    return im, d

BW = 760
def bars_card(title, sub, rows, vmax, fmt, dur=2.9, extra=None, note=None):
    n = int(dur * FPS); last = None
    for i in range(n):
        t = i / FPS; im, d = card_frame(title, sub, t)
        for k, r in enumerate(rows):
            lab, v, col = r[:3]; y = 300 + k * 118; tk = clamp((t - 0.25 - 0.12 * k) / 0.7); e = ease_out(tk)
            text(d, (110, y + 6), lab, F(40), INK)
            d.rounded_rectangle([700, y, 700 + BW, y + 64], 12, fill=(232, 236, 243))
            if e > 0: d.rounded_rectangle([700, y, 700 + max(20, BW * v * e / vmax), y + 64], 12, fill=col)
            text(d, (700 + BW + 24, y + 2), fmt(v * e) if tk > 0 else "", F(48), INK)
            if len(r) > 3 and tk >= 1: pop_text(im, (1880, y + 8), r[3], F(40), r[4], (t - 0.25 - 0.12 * k - 0.7) / 0.25, "ra")
        if extra: extra(im, d, t)
        if note: text(d, (110, 960), note, F(26, "r"), MUTE)
        emit(im); last = im
    return last

# ================= build
hook()
last = triptych("fc_stream_0004", "Parcel 1  ·  normal order", "Ground truth: OK, ship it", hold_end=0.6, stamp=False); flash(last)
last = triptych("fc_hard_0079", "Parcel 2  ·  damage no rule has seen", "Ground truth: DAMAGED (crushed corner)", hold_end=1.6); flash(last)

usd = lambda krw: krw / 1400
acc_rows = [("Rule", 54, (150, 160, 175), "missed 4", BAD), ("Claude Opus 5.5", 87, ACC, "missed 7", BAD), ("Claude Fable 5.2", 94, GOOD, "missed 0", GOOD)]
last = bars_card("Accuracy on unseen faults", "100 hard parcels: crushed corners, oil stains, Korean fragile stickers, wrong-order labels",
                 acc_rows, 100, lambda v: f"{v:.0f}", note="Normal flow (200 parcels): all three caught every fault. Gemini Flash: 83/100, not shown."); flash(last)

def cyc_band(im, d, t):
    e = ease_out((t - 0.2) / 0.5); xa, xb = 700 + BW * 4.5 / 16, 700 + BW * 6.1 / 16
    if e > 0:
        L = Image.new("RGBA", im.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
        dl.rectangle([xa, 280, xb, 760], fill=(255, 205, 70, int(110 * e))); im.alpha_composite(L)
        text(d, (xa, 768), "robot pick-and-place cycle 4.5 - 6.1 s", F(28), (190, 130, 10))
spd_rows = [("Rule", 0.5, (150, 160, 175)), ("Claude Opus 5.5", cost["opus"]["latency_med_s"], ACC), ("Claude Fable 5.2", cost["fable"]["latency_med_s"], GOOD), ("Human video coding*", 15.0, (190, 196, 206))]
last = bars_card("Decision time", "median, measured end to end (LLM via CLI)", spd_rows, 16, lambda v: f"{v:.1f} s", extra=cyc_band,
                 note="* industry figure for manual video coding of unreadable parcels. LLM ~ one robot cycle, ~3x faster than a human."); flash(last)

c_rows = [("Rule only", usd(cost["rule"]["err_krw"]), (150, 160, 175)),
          ("Opus on every parcel", usd(cost["opus"]["A"]["err_krw"] + cost["opus"]["A"]["api_krw_cli"]), API),
          ("Fable on every parcel", usd(cost["fable"]["A"]["err_krw"] + cost["fable"]["A"]["api_krw_cli"]), API),
          ("Rule → flagged 35% → Opus*", usd(cost["opus"]["B"]["err_krw"] + cost["opus"]["B"]["api_krw_direct_est"]), ACC),
          ("Rule → flagged 35% → Fable*", usd(cost["fable"]["B"]["err_krw"] + cost["fable"]["B"]["api_krw_direct_est"]), GOOD)]
last = bars_card("Cost per 10,000 parcels", "missed fault $35 · needless human check $0.04 · fault rate 0.3% · + LLM API cost",
                 c_rows, 1400, lambda v: f"${v:,.0f}", dur=3.4,
                 note="* direct-API price estimated from image tokens (not measured). Break-even: about 1.5 - 3 cents per decision."); flash(last)

# ---------- takeaway (4.5 s)
n = int(4.5 * FPS)
L3 = [("Fast enough.", "About one robot cycle, ~3x faster than a human.", WHITE),
      ("More accurate where it matters.", "Unseen damage: 0 missed vs 4 for the rule.", WHITE),
      ("Not cheaper yet.", "Route only rule-flagged parcels; get each decision under ~2-3 cents.", AMB)]
for i in range(n):
    t = i / FPS; im = Image.new("RGBA", (W, H), NAVY + (255,)); d = ImageDraw.Draw(im)
    for k, (a, b, c) in enumerate(L3):
        pop_text(im, (130, 210 + k * 210), a, F(76), c, (t - 0.15 - 0.45 * k) / 0.3)
        pop_text(im, (134, 304 + k * 210), b, F(38, "r"), (180, 190, 210), (t - 0.35 - 0.45 * k) / 0.3)
    text(d, (130, 990), "Isaac Sim simulation · 300 synthetic parcels · Nov 2026 · not field data", F(24, "r"), (120, 132, 155))
    emit(im)
ff.stdin.close(); ff.wait(); print("frames", N[0], "sec", round(N[0] / FPS, 1))
