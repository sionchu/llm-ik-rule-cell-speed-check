"""Total time per box = decision + robot motion (from results/robot_cycle.json-equivalent values measured in the Isaac cell).
Two layouts: sequential (robot waits for the decision) and pipelined (next box is decided while the robot moves the current one)."""
import json, os, statistics as st
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IND, TOTE = 6.144, 4.53                          # measured cycles (fc_stream_0004_induct, fc_hard_0079_tote)
EXC = {"REJECT", "MANUAL", "RESCAN", "RELABEL", "DAMAGED", "HOLD", "EXC"}
def cyc(pred): return TOTE if (pred in EXC or pred is None) else IND
def summ(dec, preds):
    seq = [d + cyc(p) for d, p in zip(dec, preds)]; pip = [max(d, cyc(p)) for d, p in zip(dec, preds)]
    return dict(dec_mean=round(st.mean(dec), 2), seq_mean=round(st.mean(seq), 2), pipe_mean=round(st.mean(pip), 2),
                pph_seq=round(3600 / st.mean(seq)), pph_pipe=round(3600 / st.mean(pip)))
def L(f): return [json.loads(l) for l in open(os.path.join(R, "img", f), encoding="utf-8")]
def last(rows):
    d = {}
    for r in rows:
        if r.get("status", "SUCCESS") == "SUCCESS" or r["id"] not in d: d[r["id"]] = r
    return list(d.values())
out = {}
for s in ("stream", "hard"):
    rows = json.load(open(os.path.join(R, "results", f"v2_rows_{s}.json")))
    out[f"v2_par_{s}"] = summ([r["t"] for r in rows], [r["pred"] for r in rows])
    for name, f in (("rule_vision", f"pred_rule_vision_{s}.jsonl"), ("decisions", f"pred_decisions_medium_q5_{s}.jsonl")):
        rr = [r for r in last(L(f)) if r.get("latency_s") is not None]
        out[f"{name}_{s}"] = summ([r["latency_s"] for r in rr], [r.get("pred") for r in rr])
for s in ("stream", "hard"):
    for name, f in (("rule_fc", f"pred_rule_fc_fc_{s}.jsonl"), ("opus_fc", f"pred_claude_claude-opus-5-5-low_roi_fc_{s}.jsonl"),
                    ("fable_fc", f"pred_claude_claude-fable-5-2-low_roi_fc_{s}.jsonl")):
        try:
            rr = [r for r in last(L(f)) if r.get("latency_s") is not None]
            out[f"{name}_{s}"] = summ([r["latency_s"] for r in rr], [("SHIP" if r.get("pred") in ("OK", "SHIP") else "EXC") for r in rr])
        except FileNotFoundError: pass
for k, v in out.items(): print(k, v)
json.dump(out, open(os.path.join(R, "results", "total_time.json"), "w"), indent=1)
