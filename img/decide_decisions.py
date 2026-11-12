"""Gemini Decisions API (gemini-decision-1) for the parcel cell (doc 29). One HTTP call per parcel, no CLI.
usage: python decide_decisions.py SET [ids_file]
env: GEMINI_API_KEY (required, never written to disk by this script), RES=low|medium|high|ultra_high (default medium),
     QN=1 (action choice only) | 5 (action + 4 yes/no exception questions). Writes pred_decisions_<RES>_q<QN>_<SET>.jsonl."""
import base64, http.client, io, json, os, sys, tempfile, time
os.environ["ROI"] = "1"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decide_llm_image as D
from common import criteria, POLICY

URL = "https://generativelanguage.googleapis.com/v1beta/decisions"
RES = os.environ.get("RES", "medium"); QN = int(os.environ.get("QN", "1"))
KEY = os.environ["GEMINI_API_KEY"]

CONN = None

PX = int(os.environ.get("PX", "0"))   # client-side downsize before upload (smaller request); 0 = send crop as is

def b64(p):
    if not PX: return base64.b64encode(open(p, "rb").read()).decode()
    from PIL import Image
    im = Image.open(p); im.thumbnail((PX, PX)); buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()

def questions(z):
    q = {"action": {"type": "choice", "criteria": criteria(),
                    "instructions": f"Robot parcel-sorting cell. Scale reading: {z['weight']} kg. {POLICY} Pick the one output for this parcel."}}
    if QN >= 5:
        q.update({
            "hazmat": {"type": "noul", "instructions": "Does the parcel carry a hazardous-goods label?"},
            "damaged": {"type": "noul", "instructions": "Is the package visibly damaged (torn, crushed, leaking, wet)?"},
            "address_conflict": {"type": "noul", "instructions": "Does the postal code on the label contradict the written city/district?"},
            "label_unreadable": {"type": "noul", "instructions": "Is the shipping label text unreadable or empty?"}})
    return q

def call(z, wd):
    view = os.path.join(wd, "view.jpg"); D.to_jpeg(os.path.join(D.ROOT, "cam", f"{z['id']}.png"), view)
    body = {"model": "gemini-decision-1", "input": [
        {"type": "text", "text": "Overhead camera image of the parcel at the pick point (label may be rotated), then a close-up of the shipping label."},
        {"type": "image", "data": b64(view), "mime_type": "image/jpeg", "resolution": RES},
        {"type": "image", "data": b64(os.path.join(wd, "label.jpg")), "mime_type": "image/jpeg", "resolution": RES}],
        "questions": questions(z)}
    data = json.dumps(body).encode()
    global CONN
    t0 = time.perf_counter()
    try:
        for attempt in (0, 1):   # keep-alive connection (a cell PC would hold one open); reconnect once if the server closed it
            try:
                if CONN is None: CONN = http.client.HTTPSConnection("generativelanguage.googleapis.com", timeout=60)
                CONN.request("POST", "/v1beta/decisions", data, {"Content-Type": "application/json", "x-goog-api-key": KEY})
                r = CONN.getresponse(); raw = r.read(); break
            except (http.client.HTTPException, OSError):
                CONN = None
                if attempt: raise
        dt = time.perf_counter() - t0
        if r.status != 200: return dict(status=f"HTTP {r.status}", err=raw.decode(errors="replace")[:400]), dt
        d = json.loads(raw)
        a = d.get("answers", {}); act = a.get("action", {}); u = d.get("usage", {})
        probs = act.get("probabilities") or {}
        top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
        return dict(status="SUCCESS", pred=act.get("choice"), conf=act.get("confidence"), top3=top,
                    extra={k: v.get("noul") for k, v in a.items() if k != "action"}, tok_in=u.get("total_input_tokens"),
                    tok_by_mod=u.get("input_tokens_by_modality"), req_kb=round(len(data) / 1024)), dt
    except Exception as e:
        return dict(status=f"ERR {type(e).__name__}", err=str(e)[:300]), time.perf_counter() - t0

def main():
    s = sys.argv[1]
    rows = [json.loads(l) for l in open(os.path.join(D.HERE, "sets", f"{s}.jsonl"), encoding="utf-8")]
    if len(sys.argv) > 2: ids = set(open(sys.argv[2]).read().split()); rows = [z for z in rows if z["id"] in ids]
    out = os.path.join(D.HERE, f"pred_decisions_{RES}_q{QN}{f'_px{PX}' if PX else ''}_{s}.jsonl")
    done = {j["id"] for j in map(json.loads, open(out, encoding="utf-8")) if j.get("status") == "SUCCESS"} if os.path.exists(out) else set()
    wd = tempfile.mkdtemp(prefix="parcel_dec_")
    for z in rows:
        if z["id"] in done or not os.path.exists(os.path.join(D.ROOT, "cam", f"{z['id']}.png")): continue
        env, dt = call(z, wd)
        rec = dict(id=z["id"], gold=z["action"], exc=z["exc"], form=z["form"], barcode=z["barcode"], latency_s=round(dt, 3), **env)
        with open(out, "a", encoding="utf-8") as f: f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(z["id"], env.get("pred"), z["action"], round(dt, 3), env.get("conf"), env.get("tok_in"), env.get("status"), flush=True)
        if env["status"].startswith("HTTP 4") and "429" not in env["status"]: print(env.get("err")); break
        if "429" in env["status"]: time.sleep(10)

if __name__ == "__main__":
    main()
