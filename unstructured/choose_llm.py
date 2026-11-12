"""LLM picks one of the code-verified candidates (IK ok + collision free + geometric suction ok) from the top-view image.
python choose_llm.py claude:claude-opus-5-5-low  -> pred_<model>.jsonl"""
import json, os, re, shutil, subprocess, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe")

def valid(c): return c.get("collision_free") and c["geom_ok"]

def prompt(b, cs):
    rows = "\n".join(f"- {c['cid']}: suction point {c['grasp']}, wrist {'flipped' if c['flip'] else 'normal'}, transfer height {c['transfer']}, robot move {c['move_s']:.2f} s"
                     for c in sorted(cs, key=lambda c: c["move_s"]))
    return ("You choose the pick for a suction robot in a parcel cell. Use the Read tool to view view.jpg: top view of the parcel on the belt. "
            "Blue circles 0-8 are the candidate suction-cup positions (cup size drawn to scale). "
            "The suction cup fails if any part of its circle touches a torn hole (grey-brown opening) or a wet stain (darker brown patch); "
            "packing tape (pale strip) and the white label are fine to grip. "
            f"Parcel {b['L']*100:.0f} x {b['W']*100:.0f} x {b['H']*100:.0f} cm, {b['mass']} kg. "
            "Every candidate below already passed inverse kinematics, collision check and holding-torque check:\n" + rows +
            "\nPick the candidate most likely to hold the parcel; among equally safe ones pick the shortest move. "
            "Do not run commands or code. Answer with only a JSON object: {\"cid\": \"<candidate id>\", \"confidence\": <0-1>}")

if __name__ == "__main__":
    model = sys.argv[1]; name, effort = model.split(":")[1].rsplit("-", 1)
    scenes = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(HERE, "scenes.jsonl"))}
    out = os.path.join(HERE, f"pred_{model.replace(':', '_')}.jsonl")
    done = {json.loads(l)["id"] for l in open(out)} if os.path.exists(out) else set()
    wd = tempfile.mkdtemp(prefix="upick_")
    for l in open(os.path.join(HERE, "cands.jsonl")):
        d = json.loads(l); b = scenes[d["id"]]; cs = [c for c in d["cands"] if valid(c)]
        if d["id"] in done or len({c["grasp"] for c in cs}) < 2: continue      # 0 or 1 grasp point left: nothing to choose
        shutil.copy(os.path.join(HERE, "img", f"{b['id']}.jpg"), os.path.join(wd, "view.jpg"))
        t0 = time.perf_counter()
        r = subprocess.run([CLAUDE, "-p", prompt(b, cs), "--model", name, "--effort", effort, "--output-format", "json", "--strict-mcp-config",
                            "--setting-sources", "project", "--tools", "Read", "--no-session-persistence",
                            "--system-prompt", "You are the pick-selection layer of a robot cell. Answer with JSON only."],
                           capture_output=True, text=True, encoding="utf-8", cwd=wd, timeout=300, stdin=subprocess.DEVNULL)
        dt = time.perf_counter() - t0
        try:
            j = json.loads(r.stdout); u = j.get("usage") or {}
            m = re.search(r"\{.*\}", j.get("result", ""), re.S); p = json.loads(m.group(0)) if m else {}
            rec = dict(id=d["id"], cid=p.get("cid"), conf=p.get("confidence"), latency_s=round(dt, 2), api_ms=j.get("duration_api_ms"),
                       status="ERROR" if j.get("is_error") else "SUCCESS", cost_usd_list=j.get("total_cost_usd"),
                       tok_in=(u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0), tok_out=u.get("output_tokens"))
        except Exception as e:
            rec = dict(id=d["id"], cid=None, status=f"ERR {e}"[:200], latency_s=round(dt, 2))
        with open(out, "a") as f: f.write(json.dumps(rec) + "\n")
        print(d["id"], rec.get("cid"), rec.get("latency_s"), flush=True)
