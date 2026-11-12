"""v3 F4 total time per box = decision + robot motion (same cycles as _total_time.py)."""
import json, os, statistics as st, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eval_v3 as V
IND, TOTE = 6.144, 4.53
EXC = {"REJECT", "MANUAL", "RESCAN", "RELABEL", "DAMAGED", "HOLD", "EXC"}
def cyc(p): return TOTE if (p in EXC or p is None) else IND
F4 = dict(stain=True, hole=True, sus_db=False, flag_dmg=False)
out = {}
for s in ("stream", "hard"):
    rows = V.run(s, **F4)
    d = [r["t"] for r in rows]; p = [r["pred"] for r in rows]
    seq = [a + cyc(b) for a, b in zip(d, p)]; pip = [max(a, cyc(b)) for a, b in zip(d, p)]
    out[f"v3_f4_{s}"] = dict(n=len(rows), correct=sum(r["pred"] == r["gold"] for r in rows), dec_mean=round(st.mean(d), 2),
        within_cycle=round(sum(a <= cyc(b) for a, b in zip(d, p)) / len(d), 3),
        seq_mean=round(st.mean(seq), 2), pipe_mean=round(st.mean(pip), 2), pph_seq=round(3600 / st.mean(seq)), pph_pipe=round(3600 / st.mean(pip)))
for s in ("stream", "hard"):
    sets = {z["id"]: z for z in V.E.L(f"sets/{s}.jsonl")}
    o = V.E.last_ok(V.E.L(f"pred_claude_claude-opus-5-5-low_roi_{s}.jsonl"))
    rr = [(o[i], z) for i, z in sets.items() if i in o and o[i].get("status") == "SUCCESS"]
    d = [r.get("api_ms", r["latency_s"] * 1000) / 1000 for r, z in rr]; p = [r["pred"] for r, z in rr]
    seq = [a + cyc(b) for a, b in zip(d, p)]; pip = [max(a, cyc(b)) for a, b in zip(d, p)]
    out[f"opus_alone_{s}"] = dict(n=len(rr), correct=sum(r["pred"] == z["action"] for r, z in rr), dec_mean=round(st.mean(d), 2),
        pph_seq=round(3600 / st.mean(seq)), pph_pipe=round(3600 / st.mean(pip)))
for k, v in out.items(): print(k, v)
json.dump(out, open(os.path.join(V.ROOT, "results", "total_time_v3.json"), "w"), indent=1)
