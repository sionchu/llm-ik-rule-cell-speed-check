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
        pop_text(im, (W // 2, 250), "Claude Fable 5.2 scores high as a robot agent. Does it keep up with a line?", F(40, "r"), AMB, (t - 0.0) / 0.3, "ma")
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
            mv = (m["frames"] - m["arrive_frames"]) / SRC
            el = clamp(s - A, 0, lat + mv)
            decided = s >= A + lat; done = s >= A + lat + mv
            col = (GOOD if ok else BAD) if decided else ACC
            text(d, (x + PW - 18, yb + 14), f"{el:4.1f} s", F(46), col, "ra")
            text(d, (x + PW - 18, yb + 182), f"decide {lat:.1f} s + move {mv:.1f} s" if done else ("" if not decided else "moving"), F(22, "r"), MUTE, "ra")
            bw = PW - 36; sc = 12.0; d.rounded_rectangle([x + 18, yb + 104, x + 18 + bw, yb + 118], 7, fill=(228, 232, 240))
            d.rounded_rectangle([x + 18, yb + 104, x + 18 + max(14, bw * min(el, sc) / sc), yb + 118], 7, fill=col)
            xd = x + 18 + bw * min(lat, sc) / sc
            if decided: d.line([xd, yb + 98, xd, yb + 124], fill=INK, width=3)
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
def bars_card(title, sub, rows, vmax, fmt, dur=2.9, extra=None, note=None, fmt2=None):
    n = int(dur * FPS); last = None
    for i in range(n):
        t = i / FPS; im, d = card_frame(title, sub, t)
        for k, r in enumerate(rows):
            lab, v, col = r[:3]; y = 300 + k * 118; tk = clamp((t - 0.25 - 0.12 * k) / 0.7); e = ease_out(tk)
            text(d, (110, y + 6), lab, F(40), INK)
            d.rounded_rectangle([700, y, 700 + BW, y + 64], 12, fill=(232, 236, 243))
            if e > 0: d.rounded_rectangle([700, y, 700 + max(20, BW * v * e / vmax), y + 64], 12, fill=col)
            fixed = r[5] if len(r) > 5 and tk >= 1 else None          # optional final labels, e.g. a range
            text(d, (700 + BW + 24, y - 4), (fixed[0] if fixed else fmt(v * e)) if tk > 0 else "", F(44 if fmt2 else 48), INK)
            if fmt2 and tk > 0: text(d, (700 + BW + 26, y + 46), fixed[1] if fixed else fmt2(v * e), F(28, "r"), MUTE)
            if len(r) > 3 and r[3] and tk >= 1: pop_text(im, (1880, y + 8), r[3], F(40), r[4], (t - 0.25 - 0.12 * k - 0.7) / 0.25, "ra")
        if extra: extra(im, d, t)
        if note: text(d, (110, 960), note, F(26, "r"), MUTE)
        emit(im); last = im
    return last


# ================= build (v3: three triptychs back to back, then two summary cards)
cost = json.load(open(os.path.join(R, "results", "cost10k.json")))
tt = json.load(open(os.path.join(R, "results", "total_time.json"))); t3 = json.load(open(os.path.join(R, "results", "total_time_v3.json")))
U = json.load(open(os.path.join(R, "unstructured", "results_u.json")))["summary"]
GR = (150, 160, 175)
usd = lambda krw: krw / 1400 / 10000

def bridge(line1, line2, dur=1.4):
    n = int(dur * FPS); last = None
    for i in range(n):
        t = i / FPS; im = Image.new("RGBA", (W, H), NAVY + (255,))
        pop_text(im, (W // 2, 400), line1, F(88), WHITE, t / 0.3, "ma")
        pop_text(im, (W // 2, 540), line2, F(44, "r"), AMB, (t - 0.3) / 0.3, "ma")
        emit(im); last = im
    return last

def table_card(title, sub, cols, rows, note=None, dur=4.4):
    """cols: [(header, x)], rows: [(cells[list of (text, colour)], subtexts or None)]"""
    n = int(dur * FPS); last = None
    for i in range(n):
        t = i / FPS; im, d = card_frame(title, sub, t)
        for h, x in cols: text(d, (x, 270), h, F(28), MUTE)
        d.line([110, 318, 1810, 318], fill=(214, 220, 230), width=2)
        for k, (cells, subs) in enumerate(rows):
            y = 350 + k * 128; tk = (t - 0.3 - 0.25 * k) / 0.3
            if tk <= 0: continue
            for j, ((s_, c), (h, x)) in enumerate(zip(cells, cols)):
                pop_text(im, (x, y), s_, F(46 if j else 44), c, tk)
                if subs and subs[j]: text(d, (x + 2, y + 58), subs[j], F(24, "r"), MUTE)
            d.line([110, y + 108, 1810, y + 108], fill=(232, 236, 243), width=1)
        if note: text(d, (110, 900), note[0], F(28, "r"), INK); text(d, (110, 950), note[1], F(24, "r"), MUTE)
        emit(im); last = im
    return last

hook()
last = triptych("fc_stream_0004", "Parcel 1  ·  normal order", "Ground truth: OK, ship it", hold_end=0.5, stamp=False); flash(last)
last = triptych("fc_hard_0079", "Parcel 2  ·  damage no rule has seen", "Ground truth: DAMAGED (crushed corner)", hold_end=1.3); flash(last)
last = bridge("Then what if the box lands anywhere?", "same robot, same cell · random size, pose and damage"); flash(last)

# ---------- unstructured triptych: same RB16 cell, box lands anywhere (Isaac, isaac/unstruct_video.py)
MU = json.load(open(os.path.join(R, "results", "video_u", "meta.json")))
CROP_U = (500, 40, 1320, 1060)
def src_u(key, i):
    m = MU[key]; i = int(clamp(i, 0, m["frames"] - 1)); p = os.path.join(R, "results", "video_u", key, f"{i:04d}.png")
    if p not in _cache:
        if len(_cache) > 400: _cache.clear()
        _cache[p] = Image.open(p).convert("RGB").crop(CROP_U).resize((PW, PH_IMG), Image.LANCZOS)
    return _cache[p]
def triptych_u(sid="u_006", hold_end=1.8):
    cu = next(json.loads(l) for l in open(os.path.join(R, "unstructured", "cands.jsonl")) if json.loads(l)["id"] == sid)
    pu = next(json.loads(l) for l in open(os.path.join(R, "unstructured", "pred_claude_claude-opus-5-5-low.jsonl")) if json.loads(l)["id"] == sid)
    tc = cu["t_cand_s"]; tl = pu["api_ms"] / 1000
    rows = [("rule", "TAUGHT RULE", "centre grasp · taught height", cu["t_rule_s"], "CRASH", "plan"),
            ("geom", "GEOMETRIC RULE", "fastest valid grasp · no image", tc, "DROPPED", "plan"),
            ("llm", "CLAUDE OPUS 5.5", "same candidates + image", tc + tl, "PLACED", "plan")]
    A = MU[f"{sid}_rule"]["arrive_frames"] / SRC
    def end_s(mode, lat):
        m = MU[f"{sid}_{mode}"]; ev = m["event_frame"] if m["event_frame"] is not None else m["frames"] - int(0.8 * SRC)
        return A + lat + (ev - m["arrive_frames"]) / SRC
    ends = {r[0]: end_s(r[0], r[3]) for r in rows}
    s_tot = max(A + r[3] + (MU[f"{sid}_{r[0]}"]["frames"] - MU[f"{sid}_{r[0]}"]["arrive_frames"]) / SRC for r in rows)
    frames = []; s = 0.0
    while s < s_tot:
        moving = s < A or any(A + r[3] <= s <= A + r[3] + (MU[f"{sid}_{r[0]}"]["frames"] - MU[f"{sid}_{r[0]}"]["arrive_frames"]) / SRC for r in rows)
        sp = SPEED if moving else 14.0; frames.append((s, sp)); s += sp / FPS
    frames += [(s_tot, SPEED)] * int(hold_end * FPS)
    ins = Image.open(os.path.join(R, "unstructured", "img", f"{sid}.jpg")).convert("RGB"); ins.thumbnail((320, 320))
    last = None
    for i, (s, sp) in enumerate(frames):
        tv = i / FPS; th = max(0.0, (i - (len(frames) - int(hold_end * FPS))) / FPS)
        im = Image.new("RGBA", (W, H), (244, 246, 250, 255)); d = ImageDraw.Draw(im)
        pop_text(im, (40, 34), "Parcel 3  ·  lands anywhere, wet patch near the centre", F(54), INK, tv / 0.3)
        text(d, (40, 104), "Same RB16 cell, 15 drop funnels (target in green). Code builds IK + collision-checked grasps; the deciders choose.", F(28, "r"), MUTE)
        text(d, (W - 40, 50), f"{sp:.0f}x speed" + ("  >> planning" if sp > SPEED else ""), F(26, "r"), MUTE if sp == SPEED else ACC, "ra")
        d.rounded_rectangle([30, PTOP, 30 + 330, PTOP + ins.height + 70], 14, fill=WHITE); im.paste(ins, (35, PTOP + 5))
        text(d, (40, PTOP + ins.height + 18), "Grasp candidates (top view)", F(24), INK); text(d, (40, PTOP + ins.height + 46), "image sent to the LLM", F(20, "r"), MUTE)
        text(d, (40, 640), "Candidate planning", F(26), INK); text(d, (40, 674), f"{tc:.0f} s", F(40), (200, 140, 20)); text(d, (40, 724), "CPU Python prototype,", F(20, "r"), MUTE); text(d, (40, 750), "not optimised", F(20, "r"), MUTE)
        for k, (mode, name, sub, lat, verdict, _) in enumerate(rows):
            x = PX0 + k * (PW + PG); key = f"{sid}_{mode}"; m = MU[key]
            if s < A: fi = s * SRC
            elif s < A + lat: fi = m["arrive_frames"] - 1
            else: fi = m["arrive_frames"] + (s - A - lat) * SRC
            d.rounded_rectangle([x - 4, PTOP - 4, x + PW + 4, PTOP + PH_IMG + 214], 16, fill=WHITE); im.paste(src_u(key, fi), (x, PTOP))
            yb = PTOP + PH_IMG; ok = verdict == "PLACED"
            text(d, (x + 18, yb + 16), name, F(34), INK); text(d, (x + 18, yb + 58), sub, F(22, "r"), MUTE)
            mv = ends[mode] - A - lat; el = clamp(s - A, 0, lat + mv); decided = s >= A + lat; done = s >= ends[mode]
            col = (GOOD if ok else BAD) if done else ACC
            text(d, (x + PW - 18, yb + 14), f"{el:4.1f} s", F(46), col, "ra")
            text(d, (x + PW - 18, yb + 182), f"plan {lat:.1f} s + move {mv:.1f} s" if done else ("" if not decided else "moving"), F(22, "r"), MUTE, "ra")
            bw = PW - 36; sc = 40.0; d.rounded_rectangle([x + 18, yb + 104, x + 18 + bw, yb + 118], 7, fill=(228, 232, 240))
            d.rounded_rectangle([x + 18, yb + 104, x + 18 + max(14, bw * min(el, sc) / sc), yb + 118], 7, fill=col)
            if s >= A and not decided:
                dots = "." * (1 + int(tv * 4) % 3); text(d, (x + 18, yb + 140), ("choosing" if mode == "llm" and s >= A + tc else "planning") + dots, F(34, "r"), ACC)
            if done:
                pop_text(im, (x + 18, yb + 132), {"CRASH": "hits the belt rail", "DROPPED": "cup on the wet patch, drops", "PLACED": "off the patch, into the funnel"}[verdict], F(34), col, (s - ends[mode]) / SPEED / 0.25)
                t2 = clamp((s - ends[mode]) / SPEED / 0.3); k2 = 2.2 - 1.2 * back(t2); c = GOOD if ok else BAD
                L = Image.new("RGBA", (420, 150), (0, 0, 0, 0)); dl = ImageDraw.Draw(L)
                dl.rounded_rectangle([6, 6, 414, 144], 18, outline=c + (255,), width=10); dl.text((210, 75), verdict, font=F(78), fill=c + (255,), anchor="mm")
                L = L.rotate(-8, expand=True, resample=Image.BICUBIC); L = L.resize((max(1, int(L.width * k2 * 0.8)), max(1, int(L.height * k2 * 0.8))))
                a = L.split()[3].point(lambda v: int(v * ease_out(t2 * 1.5))); L.putalpha(a)
                im.alpha_composite(L, (int(x + PW / 2 - L.width / 2), int(PTOP + 60)))
        emit(im); last = im
    return last
last = triptych_u(hold_end=1.5); flash(last)

# ---------- card 1: fixed-pose cell, per box (accuracy, rate with motion, cost)
c = cost
k = lambda m: usd(c[m]["A"]["err_krw"] + c[m]["A"]["api_krw_cli"])
cols = [("", 110), ("correct (100 hard)", 640), ("faults shipped", 960), ("boxes / h, motion incl.", 1230), ("cost per box", 1560)]
rows = [([("Rule", INK), ("54", INK), ("4", BAD), (f'{tt["rule_fc_stream"]["pph_pipe"]}', INK), (f'${usd(c["rule"]["err_krw"]):.3f}', INK)],
         ["barcode + weight + colour", None, None, f'{tt["rule_fc_stream"]["pph_seq"]} if robot waits', f'₩{usd(c["rule"]["err_krw"]) * 1400:,.0f}']),
        ([("Claude Opus 5.5", ACC), ("87", INK), ("7", BAD), (f'{tt["opus_fc_stream"]["pph_pipe"]}', INK), (f"${k('opus'):.3f}", INK)],
         ["decision ~4.6 s", None, None, f'{tt["opus_fc_stream"]["pph_seq"]} if robot waits', f"₩{k('opus') * 1400:,.0f}"]),
        ([("Claude Fable 5.2", GOOD), ("94", GOOD), ("0", GOOD), (f'{tt["fable_fc_stream"]["pph_pipe"]}', INK), (f"${k('fable'):.3f}", INK)],
         ["decision ~4.7 s", None, None, f'{tt["fable_fc_stream"]["pph_seq"]} if robot waits', f"₩{k('fable') * 1400:,.0f}"]),
        ([("Person, video", MUTE), ("-", MUTE), ("-", MUTE), ("~15 s / box", MUTE), ("$0.039-0.045", MUTE)], ["industry figure", None, None, None, "₩54-63"])]
last = table_card("Parcels 1-2: fixed box pose", "300 synthetic parcels · rate = next box decided while the robot moves (6.1 s line, 4.5 s tote)", cols, rows,
                  note=("Fits a cobot cycle, not a 1.4-2.3 s high-speed sorter (exception lane only). Every-box LLM costs more than a person.",
                        "Cost = API (CLI price) + errors: missed fault $35, fault rate 0.3%, $1 = ₩1,400. Motion program written by a coding agent in ~1 min."), dur=4.8); flash(last)

# ---------- card 2: two fixes (Opus only when unsure · boxes land anywhere)
n = int(4.4 * FPS)
L_ = [("Rule + vision", 56, GR), ("Opus on every box", 94, ACC), ("Opus only when unsure (18%)", 99, GOOD)]
R_ = [("Taught rule + vision", U["rule_taught"]["success"], GR), ("Fastest valid grasp", U["rule_geom"]["success"], (150, 120, 220)), ("Opus picks the grasp", U["llm"]["success"], GOOD)]
for i in range(n):
    t = i / FPS; im, d = card_frame("Two changes", "left: 100 hard parcels, correct · right: 40 boxes landing anywhere, handled without a person", t)
    for side, (rows_, vmax, x0, head, fmt) in enumerate(((L_, 100, 110, "Barcode ‖ Gemini Decisions → Opus only when unsure", "{:.0f}/100"),
                                                        (R_, 40, 1000, "Code builds IK + collision-checked grasps, LLM chooses", "{:.0f}/40"))):
        text(d, (x0, 262), head, F(28), MUTE)
        for kk, (lab, v, col) in enumerate(rows_):
            y = 410 + kk * 150; tk = clamp((t - 0.3 - 0.15 * kk - 0.3 * side) / 0.7); e = ease_out(tk)
            text(d, (x0, y - 46), lab, F(34), INK); d.rounded_rectangle([x0, y, x0 + 600, y + 52], 12, fill=(232, 236, 243))
            if e > 0: d.rounded_rectangle([x0, y, x0 + max(20, 600 * v * e / vmax), y + 52], 12, fill=col)
            if tk > 0: text(d, (x0 + 620, y - 4), fmt.format(v * e), F(44), INK)
    if t > 1.2:
        xc = 1000 + 600 * 23 / 40
        for kk in range(3): d.line([xc, 410 + kk * 150 - 8, xc, 410 + kk * 150 + 60], fill=(190, 130, 10), width=4)
        text(d, (xc - 56, 410 + 2 * 150 + 70), "ceiling 23", F(24), (190, 130, 10))
    text(d, (110, 900), f'Left: same rate as Opus on every box ({t3["v3_f4_hard"]["pph_pipe"]} vs {t3["opus_alone_hard"]["pph_pipe"]} /h), more accurate, Opus on 18% of boxes.', F(28, "r"), INK)
    text(d, (110, 950), "Right: synthetic top-view images, suction rules assumed; candidate planning 27 s on a CPU prototype.", F(24, "r"), MUTE)
    emit(im); last = im
flash(last)

# ---------- takeaway (4.5 s)
n = int(4.6 * FPS)
L3 = [("Fast enough for a cobot cell.", "Decide while the robot moves. Not for 1.4-2.3 s sorters: exception lane only.", WHITE),
      ("Better where rules run out.", "Unseen damage: Fable 0 missed · boxes anywhere: Opus 23/40 vs taught rule 12/40", WHITE),
      ("Cost decides the rest.", "Every box costs more than a person; only on doubtful boxes, about the rule's cost.", AMB)]
for i in range(n):
    t = i / FPS; im = Image.new("RGBA", (W, H), NAVY + (255,)); d = ImageDraw.Draw(im)
    for k2, (a, b, c2) in enumerate(L3):
        pop_text(im, (130, 210 + k2 * 210), a, F(76), c2, (t - 0.15 - 0.45 * k2) / 0.3)
        pop_text(im, (134, 304 + k2 * 210), b, F(38, "r"), (180, 190, 210), (t - 0.35 - 0.45 * k2) / 0.3)
    pop_text(im, (130, 860), "Next: faster grasp planning, then flipped boxes.", F(32, "r"), (150, 200, 255), (t - 1.8) / 0.3)
    text(d, (130, 990), "Isaac Sim + synthetic images · 300 parcels + 40 unstructured boxes · Nov 2026 · not field data", F(24, "r"), (120, 132, 155))
    emit(im)
ff.stdin.close(); ff.wait(); print("frames", N[0], "sec", round(N[0] / FPS, 1))
