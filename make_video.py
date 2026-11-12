"""LinkedIn clip: FC outbound check, rule vs LLM — speed, accuracy, cost (2026-11-12).
Inputs: results/video/<id>/NNNN.png (Isaac front view, sort_cell.py --video), cam/<id>.png (pick camera),
img/pred_*fc_*.jsonl (measured decisions + latency), results/cost10k.json (img/cost10k.py).
Output: results/FC_outbound_check_linkedin.mp4 (1920x1080, 24 fps, H.264)"""
import json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
os.environ["ROI"] = "1"
R = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(R, "img"))
import decide_llm_image as D

W, H, FPS = 1920, 1080, 24
FD = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts")
def F(sz, bold=True):
    for p in ([os.path.join(FD, "KoPub Dotum Bold.ttf"), r"C:\Windows\Fonts\malgunbd.ttf"] if bold else [os.path.join(FD, "KoPub Dotum Medium.ttf"), r"C:\Windows\Fonts\malgun.ttf"]):
        if os.path.exists(p): return ImageFont.truetype(p, sz)
NAVY, INK, MUTE, WHITE = (16, 24, 40), (28, 32, 40), (110, 118, 130), (255, 255, 255)
GOOD, BAD, ACC, API = (34, 160, 90), (214, 60, 50), (40, 110, 220), (240, 150, 40)
KO = {"OK": "정상 출고", "DAMAGED": "파손", "RELABEL": "라벨 재부착", "SPEC_OUT": "무게 불일치", "PACK_UNFIT": "포장 부적합", "MANUAL": "다른 주문 라벨"}
METHODS = [("rule", "룰 (바코드·무게·색)", "pred_rule_fc_{s}.jsonl"), ("flash", "Gemini Flash", "pred_agy_gemini-3.8-flash-low_roi_{s}.jsonl"),
           ("opus", "Claude Opus 5.5", "pred_claude_claude-opus-5-5-low_roi_{s}.jsonl"), ("fable", "Claude Fable 5.2", "pred_claude_claude-fable-5-2-low_roi_{s}.jsonl")]
HUMAN_S, SPEED = 15.0, 3.0
meta = json.load(open(os.path.join(R, "results", "video", "meta.json")))
cost = json.load(open(os.path.join(R, "results", "cost10k.json")))
PARCELS = [("fc_stream_0004", "박스 1 · 정상 주문", "정답: 정상 출고"),
           ("fc_hard_0079", "박스 2 · 처음 보는 파손", "정답: 파손 (눌린 모서리, 규칙에 없던 형태)"),
           ("fc_hard_0004", "박스 3 · 다른 주문 라벨", "정답: 다른 주문 라벨 (주문번호 불일치)")]

def pred(mk, fn, sid):
    s = sid.rsplit("_", 1)[0]
    for l in open(os.path.join(R, "img", fn.format(s=s)), encoding="utf-8"):
        j = json.loads(l)
        if j["id"] == sid: return j["pred"], j["latency_s"], j["gold"]

ff = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                       "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                       os.path.join(R, "results", "FC_outbound_check_linkedin.mp4")], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
NFR = [0]
def emit(im, n=1):
    b = im.convert("RGB").tobytes()
    for _ in range(n): ff.stdin.write(b); NFR[0] += 1

def text(d, xy, s, sz, fill=INK, bold=True, anchor="la"): d.text(xy, s, font=F(sz, bold), fill=fill, anchor=anchor)

def card(title, sub=None):
    im = Image.new("RGB", (W, H), WHITE); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=ACC); text(d, (120, 110), title, 58)
    if sub: text(d, (120, 190), sub, 30, MUTE, False)
    return im, d

# ---------- 0. title
im, d = card("물류 출고 검사에 LLM, 느리지 않나?", "Isaac Sim 출고 검사 셀 · 룰 vs Gemini Flash · Claude Opus 5.5 · Claude Fable 5.2")
text(d, (120, 330), "같은 박스 300개(합성)를 같은 카메라로 찍고, 판단 시간 · 정답 · 비용을 실측했습니다.", 34, INK, False)
text(d, (120, 400), "판정 6가지: 정상 출고 / 파손 / 라벨 재부착 / 무게 불일치 / 포장 부적합 / 다른 주문 라벨", 30, MUTE, False)
emit(im, int(3.5 * FPS))

# ---------- 1. per parcel
def inset(sid):
    w = tempfile.mkdtemp(); D.to_jpeg(os.path.join(R, "cam", f"{sid}.png"), os.path.join(w, "view.jpg"))
    v = Image.open(os.path.join(w, "view.jpg")).convert("RGB"); v.thumbnail((470, 430)); return v

def panel(base, sid, title, gold_txt, rows, t, done_note=None):
    im = base.copy(); d = ImageDraw.Draw(im, "RGBA")
    # inset (pick camera, top view)
    v = INS[sid]; x0, y0 = 30, 30
    d.rectangle([x0 - 6, y0 - 6, x0 + v.width + 6, y0 + v.height + 44], fill=(255, 255, 255, 235)); im.paste(v, (x0, y0))
    text(d, (x0, y0 + v.height + 8), "픽 카메라 (탑뷰) → 판단 입력", 24, INK)
    # right panel
    px, py, pw = 1290, 30, 600
    d.rounded_rectangle([px, py, px + pw, py + 560], 18, fill=(16, 24, 40, 228))
    text(d, (px + 28, py + 24), "판단 시간 (실측)", 32, WHITE); text(d, (px + pw - 28, py + 30), f"{t:4.1f} s  ·  {SPEED:.0f}배속", 24, (180, 190, 205), False, "ra")
    bx, bw, smax = px + 28, pw - 56, 17.0
    cyc = meta[sid]["cycle_s"]; cx = bx + bw * cyc / smax
    for k, (lab, lat, p, ok) in enumerate(rows):
        y = py + 96 + k * 84
        text(d, (bx, y), lab, 24, WHITE, False)
        d.rounded_rectangle([bx, y + 34, bx + bw, y + 58], 6, fill=(255, 255, 255, 30))
        fr = min(t, lat) / smax
        col = (150, 160, 175) if t < lat else (GOOD if ok else BAD)
        if fr > 0: d.rounded_rectangle([bx, y + 34, bx + max(12, bw * fr), y + 58], 6, fill=col)
        if t >= lat:
            text(d, (bx + bw, y), (f"{lat:.1f} s  " if p else f"약 {lat:.0f} s  ") + ((KO[p] + ("" if ok else " (오답)")) if p else ""), 24, col, True, "ra")
    d.line([cx, py + 120, cx, py + 520], fill=(255, 210, 80, 255), width=3)
    text(d, (cx + 6, py + 524), f"로봇 1사이클 {cyc:.1f} s", 22, (255, 210, 80))
    # caption bar
    d.rectangle([0, H - 120, W, H], fill=(16, 24, 40, 235))
    text(d, (40, H - 100), title, 38, WHITE); text(d, (40, H - 48), gold_txt, 28, (190, 200, 215), False)
    if done_note: text(d, (W - 40, H - 80), done_note, 30, (255, 210, 80), True, "ra")
    return im

INS = {sid: inset(sid) for sid, _, _ in PARCELS}
for sid, title, gold_txt in PARCELS:
    rows = []
    for mk, lab, fn in METHODS:
        p, lat, g = pred(mk, fn, sid); rows.append((lab, lat, p, p == g))
    rows.append(("사람 영상 코딩 (업계 자료)", HUMAN_S, None, True))
    fr_dir = os.path.join(R, "results", "video", sid); m = meta[sid]
    frames = [os.path.join(fr_dir, f"{i:04d}.png") for i in range(m["frames"])]
    for f in frames[: m["arrive_frames"]]: emit(panel(Image.open(f), sid, title, gold_txt, rows, 0.0))
    last = Image.open(frames[m["arrive_frames"] - 1]); tmax = max(r[1] for r in rows) + 0.6
    for k in range(int(tmax / SPEED * FPS) + 1): emit(panel(last, sid, title, gold_txt, rows, k * SPEED / FPS))
    note = "로봇은 Fable 판정대로 → " + ("정상 라인" if m["dest"] == "induct" else "예외 토트")
    for f in frames[m["arrive_frames"]:]: emit(panel(Image.open(f), sid, title, gold_txt, rows, tmax, note))
    emit(panel(Image.open(frames[-1]), sid, title, gold_txt, rows, tmax, note), int(0.8 * FPS))

# ---------- 2. accuracy
def hbar(d, x, y, w, frac, col, h=40): d.rounded_rectangle([x, y, x + max(8, w * frac), y + h], 8, fill=col)
im, d = card("성공률: 처음 보는 파손에서 차이가 납니다", "어려운 세트 100건 (오류 86건, 눌린 모서리 · 기름 얼룩 · 한글 스티커 · 다른 주문 라벨 포함)")
acc = [("룰 (바코드·무게·색)", 54, 4), ("Gemini Flash", 83, 7), ("Claude Opus 5.5", 87, 7), ("Claude Fable 5.2", 94, 0)]
text(d, (620, 300), "정답 / 100", 26, MUTE, False); text(d, (1640, 300), "오류를 OK로 통과", 26, MUTE, False)
for k, (lab, ok, miss) in enumerate(acc):
    y = 350 + k * 120; text(d, (120, y + 4), lab, 32)
    d.rounded_rectangle([620, y, 1520, y + 48], 8, fill=(235, 238, 243)); hbar(d, 620, y, 900, ok / 100, ACC if k < 3 else GOOD, 48)
    text(d, (620 + 900 * ok / 100 - 14, y + 6), f"{ok}", 32, WHITE, True, "ra"); text(d, (1740, y + 4), f"{miss}건", 34, BAD if miss else GOOD, True, "ma")
text(d, (120, 860), "일반 흐름 200건(오류 9건)은 네 방식 모두 오류를 다 잡음. 차이는 정상 박스를 사람에게 보낸 수: 룰 62 · Fable 27 · Flash 23 · Opus 15", 26, MUTE, False)
emit(im, int(5.5 * FPS))

# ---------- 3. speed
im, d = card("속도: LLM 판단은 로봇 한 사이클과 같은 수준입니다", "판단 시간 중앙값 (Claude · Gemini는 CLI 호출 왕복 실측, GPU 공유 상태)")
sp = [("룰", 0.5), ("Claude Opus 5.5", cost["opus"]["latency_med_s"]), ("Claude Fable 5.2", cost["fable"]["latency_med_s"]), ("Gemini Flash", cost["flash"]["latency_med_s"]), ("사람 영상 코딩 (업계 자료)", HUMAN_S)]
cyc = meta["fc_stream_0004"]["cycle_s"]
for k, (lab, s) in enumerate(sp):
    y = 330 + k * 100; text(d, (120, y + 4), lab, 32)
    hbar(d, 620, y, 1100, s / 16, (150, 160, 175) if s >= HUMAN_S else ACC, 44); text(d, (630 + 1100 * s / 16, y + 6), f"{s:.1f} s", 30, INK)
c0 = min(m["cycle_s"] for m in meta.values()); c1 = max(m["cycle_s"] for m in meta.values())
xa, xb = 620 + 1100 * c0 / 16, 620 + 1100 * c1 / 16
d.rectangle([xa, 310, xb, 820], fill=(255, 236, 190)); d.line([xa, 310, xa, 820], fill=(230, 170, 30), width=3); d.line([xb, 310, xb, 820], fill=(230, 170, 30), width=3)
text(d, (xa, 826), f"로봇 픽앤플레이스 1사이클 {c0:.1f}~{c1:.1f} s (Isaac, RB16, 토트 · 정상 라인)", 26, (200, 140, 20))
for k, (lab, s) in enumerate(sp):
    y = 330 + k * 100; hbar(d, 620, y, 1100, s / 16, (150, 160, 175) if s >= HUMAN_S else ACC, 44); text(d, (630 + 1100 * s / 16, y + 6), f"{s:.1f} s", 30, INK)
text(d, (120, 900), "카메라를 한 칸 앞에 두면 로봇이 판단을 기다리지 않음 (설계 추론, 미검증)", 28, MUTE, False)
emit(im, int(5.5 * FPS))

# ---------- 4. cost
im, d = card("비용: 관건은 속도가 아니라 건당 판단 비용", "1만 건당 비용 (오류율 0.3% 가정 · 놓친 오류 1건 $35 · 불필요한 사람 확인 1건 55원)")
def man(x): return x / 1e4
rows = [("룰만", cost["rule"]["err_krw"], 0, "실측"),
        ("Opus 전 박스 (CLI 실측 단가)", cost["opus"]["A"]["err_krw"], cost["opus"]["A"]["api_krw_cli"], "실측"),
        ("Fable 전 박스 (CLI 실측 단가)", cost["fable"]["A"]["err_krw"], cost["fable"]["A"]["api_krw_cli"], "실측"),
        ("룰 → 예외 35%만 Opus (직접 API)", cost["opus"]["B"]["err_krw"], cost["opus"]["B"]["api_krw_direct_est"], "추정"),
        ("룰 → 예외 35%만 Fable (직접 API)", cost["fable"]["B"]["err_krw"], cost["fable"]["B"]["api_krw_direct_est"], "추정")]
smax = 190e4; bx, bw = 760, 1000
d.rectangle([bx, 280, bx + 26, 306], fill=ACC); text(d, (bx + 36, 280), "오류 · 사람 확인 비용", 24, INK, False)
d.rectangle([bx + 330, 280, bx + 356, 306], fill=API); text(d, (bx + 366, 280), "LLM API 비용", 24, INK, False)
for k, (lab, e, a, tag) in enumerate(rows):
    y = 340 + k * 104; text(d, (120, y + 6), lab, 28)
    we, wa = bw * e / smax, bw * a / smax
    d.rectangle([bx, y, bx + we, y + 46], fill=ACC); d.rectangle([bx + we, y, bx + we + wa, y + 46], fill=API)
    text(d, (bx + we + wa + 12, y + 8), f"{man(e + a):.0f}만 원  ({tag})", 28, INK)
text(d, (120, 880), "손익분기: 건당 판단 비용 약 20~40원. 직접 API 단가는 이미지 토큰 기준 추정(미측정), Flash 비용은 미측정.", 26, MUTE, False)
emit(im, int(7 * FPS))

# ---------- 5. conclusion
im, d = card("결론")
L = [("느리다?", f"아니요. LLM 판단 약 {cost['fable']['latency_med_s']:.1f}초, 로봇 1사이클({c0:.1f}~{c1:.1f}초)과 같은 수준, 사람 15초의 1/3"),
     ("더 정확?", "처음 보는 파손에서 그렇습니다. Fable 오류 통과 0건, 룰 4건 (어려운 100건)"),
     ("더 싸다?", "아직은 아닙니다. 전 박스 호출 시 API 비용이 절감액보다 큼"),
     ("그래서", "룰이 의심한 박스만 LLM에 넘기고, 건당 판단 비용을 20~40원 아래로 → 소형 모델 증류가 다음 과제")]
for k, (q, a) in enumerate(L):
    y = 250 + k * 150; text(d, (120, y), q, 40, ACC); text(d, (420, y + 4), a, 34, INK, False)
text(d, (120, 930), "Isaac Sim 시뮬레이션 · 합성 박스 300개 · 2026-11 · 실제 현장 수치 아님", 24, MUTE, False)
emit(im, int(7 * FPS))
ff.stdin.close(); ff.wait(); print("frames", NFR[0], "sec", NFR[0] / FPS)
