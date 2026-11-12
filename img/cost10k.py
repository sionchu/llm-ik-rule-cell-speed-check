"""Per-10,000-parcel cost incl. LLM API cost (2026-11-12, for the LinkedIn clip).
Error cost = missed faults x $35 + unneeded human checks x 55 KRW (same model as analyze_fc.py, fault rate 0.3%).
API cost: (1) measured = cost_usd_list reported by the Claude CLI per call (includes the CLI's own system prompt -> upper bound);
(2) direct-API estimate = our prompt + 2 images only, image tokens = w*h/750 (Anthropic vision rule of thumb), Opus 5.5 $4/$20 per MTok;
Fable 5.2 = Opus estimate x (Fable/Opus measured CLI cost ratio). Flash via agy reports no cost -> UNKNOWN.
Output: results/cost10k.json"""
import json, os, sys, tempfile, statistics as st
os.environ["ROI"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE); sys.path.insert(0, HERE)
import analyze_fc as A          # re-runs the tables (prints) and gives rd/score/per10k/sets/gold
import decide_llm_image as D
from PIL import Image
USD = A.USD; RATE = A.RATE
sets, gold = A.sets, A.gold
R = {s: A.rd(os.path.join(HERE, f"pred_rule_fc_{s}.jsonl")) for s in sets}
LL = {"opus": "claude_claude-opus-5-5-low", "fable": "claude_claude-fable-5-2-low", "flash": "agy_gemini-3.8-flash-low"}

# direct-API token estimate on 20 sample parcels
w = tempfile.mkdtemp(); itok = []
for z in sets["fc_stream"][:10] + sets["fc_hard"][:10]:
    D.to_jpeg(os.path.join(ROOT, "cam", f"{z['id']}.png"), os.path.join(w, "view.jpg"))
    t = 0
    for n in ("view", "label"):
        im = Image.open(os.path.join(w, f"{n}.jpg")); W, H = im.size; s = min(1, 1568 / max(W, H), (1.15e6 / (W * H)) ** 0.5)
        t += (W * s) * (H * s) / 750
    itok.append(t)
prompt_tok = 900                       # policy + criteria + order text, ~3 chars/token (estimate)
est_in = st.mean(itok) + prompt_tok
out = {"direct_est": {"image_tokens": round(st.mean(itok)), "input_tokens": round(est_in)}}

def pool(m):
    P = {s: A.rd(os.path.join(HERE, f"pred_{LL[m]}_roi_{s}.jsonl")) for s in sets}
    return P

def errcost(pred_by_set):
    sh = A.score(list(pred_by_set["fc_hard"]), pred_by_set["fc_hard"], gold); ss = A.score(list(pred_by_set["fc_stream"]), pred_by_set["fc_stream"], gold)
    return A.per10k(sh, dict(fa=sh["fa"] + ss["fa"], nok=sh["nok"] + ss["nok"]))

rule_pred = {s: {i: R[s][i]["pred"] for i in R[s]} for s in sets}
m_, f_, c_ = errcost(rule_pred)
# rule-flag share on a 0.3% mix
okf = sum(p != "OK" for s in sets for i, p in rule_pred[s].items() if gold[i] == "OK") / sum(gold[i] == "OK" for s in sets for i in rule_pred[s])
ff = sum(p != "OK" for s in sets for i, p in rule_pred[s].items() if gold[i] != "OK") / sum(gold[i] != "OK" for s in sets for i in rule_pred[s])
calls_B = 10000 * ((1 - RATE) * okf + RATE * ff)
out["rule"] = dict(miss=m_, fa=f_, err_krw=c_, api_krw=0)
out["gate_B_calls_per10k"] = round(calls_B)
for m in LL:
    P = pool(m)
    cli = [j.get("cost_usd_list") for s in sets for j in P[s].values() if j.get("cost_usd_list")]
    lat = st.median([j["latency_s"] for s in sets for j in P[s].values()])
    cli_usd = st.mean(cli) if cli else None
    pa = {s: {i: P[s][i]["pred"] for i in P[s]} for s in sets}
    pb = {s: {i: (P[s][i]["pred"] if rule_pred[s].get(i, "OK") != "OK" else "OK") for i in P[s]} for s in sets}
    ma, fa_, ca = errcost(pa); mb, fb, cb = errcost(pb)
    out[m] = dict(latency_med_s=lat, cli_usd_per_call=cli_usd,
                  A=dict(miss=ma, fa=fa_, err_krw=ca, calls=10000), B=dict(miss=mb, fa=fb, err_krw=cb, calls=round(calls_B)))
opus_out = st.mean([j["tok_out"] for s in sets for j in pool("opus")[s].values()])
opus_est = (est_in * 4 + opus_out * 20) / 1e6
out["opus"]["direct_usd_per_call_est"] = opus_est
out["fable"]["direct_usd_per_call_est"] = opus_est * out["fable"]["cli_usd_per_call"] / out["opus"]["cli_usd_per_call"]
out["flash"]["direct_usd_per_call_est"] = None
for m in LL:
    for g in ("A", "B"):
        d = out[m][g]
        d["api_krw_cli"] = d["calls"] * out[m]["cli_usd_per_call"] * USD if out[m]["cli_usd_per_call"] else None
        d["api_krw_direct_est"] = d["calls"] * out[m]["direct_usd_per_call_est"] * USD if out[m]["direct_usd_per_call_est"] else None
os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "results", "cost10k.json"), "w"), indent=1)
print(json.dumps(out, indent=1, ensure_ascii=False))
