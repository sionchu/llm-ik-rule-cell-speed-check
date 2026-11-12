"""v2 parcel decision pipeline, evaluated offline from stored predictions (no new API calls).
barcode + scale + red check (rule) -> damage check (damage_check.py dark_brown) -> Decisions q5 once
-> Opus (stored roi preds) only for damage-suspect / low-confidence / flagged parcels.
Thresholds chosen on stream, applied unchanged to hard. Output: results/RESULTS_v2.md + results/v2_eval.json"""
import json, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
def L(f):
    p = os.path.join(HERE, f)
    return [json.loads(l) for l in open(p, encoding="utf-8")] if os.path.exists(p) else []
def last_ok(rows):
    d = {}
    for r in rows:
        if r.get("status", "SUCCESS") == "SUCCESS" or r["id"] not in d: d[r["id"]] = r
    return d

T_HI, T_LO, CONF, FLAG = 0.042, 0.030, 0.60, 0.50   # stream-calibrated (see RESULTS_v2.md)
def q(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]

def run(s, t_hi=T_HI, t_lo=T_LO, conf=CONF, flag=FLAG, use_flags=True, par=False):
    """par=False: Decisions only when barcode fails / damage-suspect (sequential).
    par=True : Decisions called for every parcel in parallel with barcode+checks (time = max of the two); its hazmat flag -> MANUAL."""
    sets = {z["id"]: z for z in L(f"sets/{s}.jsonl")}
    rv = last_ok(L(f"pred_rule_vision_{s}.jsonl")); dc = last_ok(L(f"pred_decisions_medium_q5_{s}.jsonl"))
    dfeat = json.load(open(os.path.join(HERE, f"damage_feat_{s}.json")))
    op = last_ok(L(f"pred_claude_claude-opus-5-5-low_roi_{s}.jsonl"))
    o_api = st.median(o["api_ms"] / 1000 for o in op.values() if o.get("api_ms")); o_cli = st.median(o["latency_s"] for o in op.values() if o.get("status") == "SUCCESS")
    out = []
    for i, z in sorted(sets.items()):
        r = rv[i]; ev = r["evidence"]; stg = r.get("stages", {}); d = dc.get(i, {})
        fl = (d.get("extra") or {}) if use_flags else {}
        fast = stg.get("barcode_s", 0) + stg.get("checks_s", 0) + dfeat[i]["s"]
        t = max(fast, d.get("latency_s", 0)) if par else fast; t_cli = t; path = "rule"
        db = dfeat[i]["dark_brown"]
        if db >= t_hi: pred = "REJECT"
        elif ev.get("red", 0) > 0.0015 or z["weight"] > 30: pred = "MANUAL"
        elif par and fl.get("hazmat", 0) >= flag: pred = "MANUAL"; path = "decisions_flag"
        elif ev.get("barcode") and db < t_lo and not (par and max(fl.get("damaged", 0), fl.get("address_conflict", 0)) >= flag):
            pred = ev["barcode"]; path = "barcode"
        else:
            if not par: t += d.get("latency_s", 0); t_cli = t
            pred = d.get("pred"); path = "decisions"
            if pred is None or db >= t_lo or d.get("conf", 0) < conf or max(fl.get("damaged", 0), fl.get("address_conflict", 0)) >= flag:
                o = op.get(i)
                if o and o.get("status") == "SUCCESS":
                    pred = o["pred"]; path = "opus"; t += o.get("api_ms", o["latency_s"] * 1000) / 1000; t_cli += o["latency_s"]
                else: path = "opus_NOT_RUN"; t += o_api; t_cli += o_cli   # Opus not measured on this parcel: keep Decisions answer, charge median Opus time
        out.append(dict(id=i, exc=z["exc"], gold=z["action"], pred=pred, path=path, t=t, t_cli=t_cli))
    return out

def summ(rows):
    n = len(rows); ok = sum(r["pred"] == r["gold"] for r in rows)
    dmg = [r for r in rows if r["exc"].startswith("damaged")]
    exc = [r for r in rows if r["exc"] != "none"]
    ts = [r["t"] for r in rows]; tc = [r["t_cli"] for r in rows]
    paths = {}
    for r in rows: paths[r["path"]] = paths.get(r["path"], 0) + 1
    return dict(n=n, correct=ok, dmg_caught=f'{sum(r["pred"]=="REJECT" for r in dmg)}/{len(dmg)}',
                exc_correct=f'{sum(r["pred"]==r["gold"] for r in exc)}/{len(exc)}',
                normal_correct=f'{sum(r["pred"]==r["gold"] for r in rows if r["exc"]=="none")}/{n-len(exc)}',
                false_reject=sum(r["pred"] == "REJECT" and not r["exc"].startswith("damaged") for r in rows),
                opus_share=round(paths.get("opus", 0) / n, 3), paths=paths,
                t_p50=round(q(ts, .5), 2), t_p95=round(q(ts, .95), 2), t_mean=round(st.mean(ts), 2),
                tcli_p50=round(q(tc, .5), 2), tcli_mean=round(st.mean(tc), 2))

def base(s, f):
    d = last_ok(L(f.format(s=s))); sets = {z["id"]: z for z in L(f"sets/{s}.jsonl")}
    rows = [dict(id=i, exc=z["exc"], gold=z["action"], pred=d.get(i, {}).get("pred"), path="x",
                 t=d[i].get("latency_s", 0) if i in d else 0, t_cli=d[i].get("latency_s", 0) if i in d else 0) for i, z in sets.items()]
    return summ(rows)

if __name__ == "__main__":
    res = {}
    for s in ("stream", "hard"):
        res[s] = {"v2": summ(run(s)), "v2_noflags": summ(run(s, use_flags=False)), "v2_par": summ(run(s, par=True)),
                  "rule_vision": base(s, "pred_rule_vision_{s}.jsonl"),
                  "decisions_q5": base(s, "pred_decisions_medium_q5_{s}.jsonl"),
                  "opus_roi": base(s, "pred_claude_claude-opus-5-5-low_roi_{s}.jsonl")}
        json.dump(run(s, par=True), open(os.path.join(ROOT, "results", f"v2_rows_{s}.json"), "w"), indent=0)
    # sensitivity on stream only (threshold choice), reported for transparency
    sens = {f"lo{lo}_hi{hi}_c{c}": summ(run("stream", hi, lo, c)) for lo in (0.025, 0.030, 0.035) for hi in (0.040, 0.042, 0.045) for c in (0.5, 0.6, 0.7)}
    res["stream_sensitivity"] = {k: (v["correct"], v["dmg_caught"], v["opus_share"], v["t_mean"]) for k, v in sens.items()}
    json.dump(res, open(os.path.join(ROOT, "results", "v2_eval.json"), "w"), indent=1, ensure_ascii=False)
    for s in ("stream", "hard"):
        for k, v in res[s].items(): print(s, k, json.dumps({kk: vv for kk, vv in v.items()}, ensure_ascii=False))
    for k, v in res["stream_sensitivity"].items(): print("sens", k, v)
