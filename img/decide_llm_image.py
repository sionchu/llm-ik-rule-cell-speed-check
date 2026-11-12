"""LLM decision from the Isaac pick-camera image (+ scale reading), one call per parcel, wall-clock latency.
usage: python decide_llm_image.py MODEL SET [ids_file]
MODEL: claude:<model>-<effort> (Claude Code CLI, Read tool only) | agy:<model> (Antigravity CLI) | local:<name> (llama-server)."""
import base64, json, os, re, shutil, subprocess, sys, tempfile, time
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import criteria, POLICY
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
CLAUDE = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")
AGY = os.environ.get("AGY", os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"))
ENDPOINT = os.environ.get("ENDPOINT", "http://127.0.0.1:8080/v1/chat/completions")

def prompt(z, attach_note):
    if "order" in z:                                  # FC outbound-check variant (doc 28 sec. 8)
        import fc_common as fc
        crit = "\n".join(f"- {k}: {v}" for k, v in fc.criteria().items())
        return (f"You are the outbound-check decision layer of a fulfilment-centre packing line, just before sorter induction. {attach_note} "
                f"It is the overhead camera image of the packed parcel (the label may be rotated).\n{fc.order_text(z)}\n{fc.POLICY}\n"
                f"Outputs:\n{crit}\n\nDo not run any commands or code: judge from viewing the image yourself. "
                'Answer with only a JSON object: {"action": "<one output name>", "confidence": <0-1>}')
    crit = "\n".join(f"- {k}: {v}" for k, v in criteria().items())
    return (f"You are the decision layer of a robot parcel-sorting cell. {attach_note} It is the overhead camera image of the parcel "
            f"at the pick point (the label may be rotated). Scale reading: {z['weight']} kg. Pick exactly one output.\n{POLICY}\n"
            f"Outputs:\n{crit}\n\nDo not run any commands or code: judge from viewing the image yourself. "
            'Answer with only a JSON object: {"action": "<one output name>", "confidence": <0-1>}')

ROI = os.environ.get("ROI") == "1"   # ROI mode: parcel crop (view.jpg) + label crop at native resolution (label.jpg), like a label-ROI OCR station

def to_jpeg(src, dst):
    im = Image.open(src).convert("RGB")
    if not ROI:
        im.save(dst, quality=90); return
    import numpy as np
    a = np.asarray(im).astype(int); r, g, b = a[..., 0], a[..., 1], a[..., 2]
    card = (r > 150) & (g > 120) & (b > 70) & (r - b > 25); white = (r > 225) & (g > 225) & (b > 225) & (abs(r - b) < 10)
    ys, xs = np.nonzero(card)
    if len(xs) > 1000:
        y0, y1, x0, x1 = [int(v) for v in (np.percentile(ys, 0.5), np.percentile(ys, 99.5), np.percentile(xs, 0.5), np.percentile(xs, 99.5))]
        pad = 40; box = (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad)); pc = im.crop(box)
    else:
        box = (0, 0, im.width, im.height); pc = im
    pc.save(dst, quality=90)
    import cv2
    sub = (white[box[1]:box[3], box[0]:box[2]]).astype(np.uint8)
    sub = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))     # merge label paper across barcode bars / text
    n, lbl, stats, _ = cv2.connectedComponentsWithStats(sub)
    lab = pc; ys = xs = []
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])); ys, xs = np.nonzero(lbl == k)
    if len(xs) > 2000:
        y0, y1, x0, x1 = [int(v) for v in (np.percentile(ys, 1), np.percentile(ys, 99), np.percentile(xs, 1), np.percentile(xs, 99))]
        pad = 30; lab = pc.crop((max(0, x0 - pad), max(0, y0 - pad), min(pc.width, x1 + pad), min(pc.height, y1 + pad)))
    lab.save(os.path.join(os.path.dirname(dst), "label.jpg"), quality=92)

NOTE_C = "Use the Read tool to view view.jpg (the parcel) and label.jpg (close-up of the shipping label) in the current directory." if ROI else "Use the Read tool to view the file view.jpg in the current directory."
NOTE_A = "The files view.jpg (the parcel) and label.jpg (label close-up) in the current workspace are the images." if ROI else "The file view.jpg in the current workspace is the image."

def call(model, z, wd):
    img = os.path.join(wd, "view.jpg"); to_jpeg(os.path.join(ROOT, "cam", f"{z['id']}.png"), img)
    t0 = time.perf_counter(); env = {}
    try:
        if model.startswith("claude:"):
            name, effort = model.split(":")[1].rsplit("-", 1)
            cmd = [CLAUDE, "-p", prompt(z, NOTE_C), "--model", name,
                   "--effort", effort, "--output-format", "json", "--strict-mcp-config", "--setting-sources", "project", "--tools", "Read",
                   "--no-session-persistence", "--system-prompt", "You are the decision layer of a robot parcel-sorting cell. Answer with JSON only."]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=wd, timeout=300, stdin=subprocess.DEVNULL)
            d = json.loads(r.stdout); u = d.get("usage") or {}
            env = dict(status="ERROR" if d.get("is_error") else "SUCCESS", response=d.get("result", ""), api_ms=d.get("duration_api_ms"),
                       tok_in=(u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0),
                       tok_out=u.get("output_tokens"), cost_usd_list=d.get("total_cost_usd"))
        elif model.startswith("agy:"):
            r = subprocess.run([AGY, "-p", prompt(z, NOTE_A), "--model", model[4:],
                                "--output-format", "json", "--mode", "plan"], capture_output=True, text=True, encoding="utf-8", cwd=wd, timeout=300)
            d = json.loads(r.stdout); u = d.get("usage") or {}
            env = dict(status=d.get("status"), response=d.get("response", ""), err=d.get("error"), tok_in=u.get("input_tokens"),
                       tok_out=(u.get("output_tokens") or 0) + (u.get("thinking_tokens") or 0))
        else:
            import urllib.request
            im = Image.open(img); im.thumbnail((1536, 1536)); im.save(img, quality=90)   # local: 3072 px timed out (300 s); Claude also downsizes to ~1568 px
            b64 = base64.b64encode(open(img, "rb").read()).decode()
            extra = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(open(os.path.join(wd, "label.jpg"), "rb").read()).decode()}}] if ROI else []
            body = json.dumps({"messages": [{"role": "user", "content": [{"type": "text", "text": prompt(z, "Two images are attached: a close-up of the shipping label, then the whole parcel." if ROI else "The image is attached.")}] + extra + [
                               {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}]}], "temperature": 0, "max_tokens": 80}).encode()
            d = json.load(urllib.request.urlopen(urllib.request.Request(ENDPOINT, body, {"Content-Type": "application/json"}), timeout=300))
            u = d.get("usage") or {}
            env = dict(status="SUCCESS", response=d["choices"][0]["message"]["content"], tok_in=u.get("prompt_tokens"), tok_out=u.get("completion_tokens"))
    except Exception as e:
        env = dict(status=f"ERR {type(e).__name__}", response="", err=str(e)[:300])
    return env, time.perf_counter() - t0

def main():
    model, s = sys.argv[1], sys.argv[2]
    rows = [json.loads(l) for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8")]
    if len(sys.argv) > 3: ids = set(open(sys.argv[3]).read().split()); rows = [z for z in rows if z["id"] in ids]
    out = os.path.join(HERE, f"pred_{model.replace(':', '_')}{'_roi' if ROI else ''}_{s}.jsonl")
    done = {j["id"] for j in map(json.loads, open(out, encoding="utf-8")) if j.get("status") == "SUCCESS"} if os.path.exists(out) else set()
    wd = tempfile.mkdtemp(prefix="parcel_img_")
    for z in rows:
        if z["id"] in done or not os.path.exists(os.path.join(ROOT, "cam", f"{z['id']}.png")): continue
        env, dt = call(model, z, wd)
        m = re.search(r"\{.*\}", env.get("response") or "", re.S); pred = conf = None
        if m:
            try: j = json.loads(m.group(0)); pred, conf = j.get("action"), j.get("confidence")
            except Exception: pass
        rec = dict(id=z["id"], pred=pred, gold=z["action"], exc=z["exc"], form=z["form"], barcode=z["barcode"], conf=conf, latency_s=round(dt, 2),
                   **{k: v for k, v in env.items() if k != "response"})
        with open(out, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(z["id"], pred, z["action"], round(dt, 1), flush=True)

if __name__ == "__main__":
    main()
