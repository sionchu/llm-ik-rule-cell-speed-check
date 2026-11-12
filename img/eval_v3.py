"""v3 case comparison from stored predictions (no new API calls). Builds on eval_v2.run (parallel form).
Cases: v2 baseline, lowered suspect band (v2 dark_brown only), v3 stain colour rule, v3 with lighter Opus routing, Fable as escalation model.
Thresholds chosen on stream; hard is held out. Output: results/v3_eval.json, printed table."""
import json, os, statistics as st
import eval_v2 as E
HERE = E.HERE; ROOT = E.ROOT
COST = dict(dec=0.0002, opus=0.016, fable=0.032)   # USD/call. dec, opus from doc 29 §8; fable = opus x2 (CLI list-cost ratio 0.135/0.068) -> estimate
STAIN_REJ, STAIN_SUS = 0.010, 0.003               # stream: wet min 0.067, non-damaged max 0.0003
HOLE_REJ, HOLE_SUS = 0.008, 0.005                 # stream: torn min 0.018, non-damaged max 0.0033

def run(s, t_hi=E.T_HI, t_lo=E.T_LO, conf=E.CONF, flag=E.FLAG, stain=False, sus_db=True, esc="opus", flag_dmg=True, hole=False):
    sets = {z["id"]: z for z in E.L(f"sets/{s}.jsonl")}
    rv = E.last_ok(E.L(f"pred_rule_vision_{s}.jsonl")); dc = E.last_ok(E.L(f"pred_decisions_medium_q5_{s}.jsonl"))
    f2 = json.load(open(os.path.join(HERE, f"damage_feat_{s}.json"))); f3 = json.load(open(os.path.join(HERE, f"damage_feat3_{s}.json")))
    llm = E.last_ok(E.L(f"pred_claude_claude-{'opus-5-5' if esc == 'opus' else 'fable-5-2'}-low_roi_{s}.jsonl"))
    out = []
    for i, z in sorted(sets.items()):
        r = rv[i]; ev = r["evidence"]; stg = r.get("stages", {}); d = dc.get(i, {}); fl = d.get("extra") or {}
        fast = stg.get("barcode_s", 0) + stg.get("checks_s", 0) + (0 if hole else f2[i]["s"]) + (f3[i]["s"] if stain else 0)   # hole=True: v3 replaces v2 dark_brown
        t = max(fast, d.get("latency_s", 0)); path = "rule"; calls = ["dec"]
        db, sn, hl = (0 if hole else f2[i]["dark_brown"]), f3[i]["stain"], f3[i]["hole"]
        susp = (sus_db and db >= t_lo) or (stain and sn >= STAIN_SUS) or (hole and hl >= HOLE_SUS)
        fdm = max(fl.get("damaged", 0) if flag_dmg else 0, fl.get("address_conflict", 0))
        if db >= t_hi or (stain and sn >= STAIN_REJ) or (hole and hl >= HOLE_REJ): pred = "REJECT"
        elif ev.get("red", 0) > 0.0015 or z["weight"] > 30: pred = "MANUAL"
        elif fl.get("hazmat", 0) >= flag: pred = "MANUAL"; path = "decisions_flag"
        elif ev.get("barcode") and not susp and fdm < flag: pred = ev["barcode"]; path = "barcode"
        else:
            pred = d.get("pred"); path = "decisions"
            if pred is None or susp or d.get("conf", 0) < conf or fdm >= flag:
                o = llm.get(i)
                if o and o.get("status") == "SUCCESS":
                    pred = o["pred"]; path = esc; calls.append(esc); t += o.get("api_ms", o["latency_s"] * 1000) / 1000
                else: path = esc + "_NOT_RUN"
        out.append(dict(id=i, exc=z["exc"], gold=z["action"], pred=pred, path=path, t=t, t_cli=t, cost=sum(COST[c] for c in calls)))
    return out

def summ(rows):
    s = E.summ(rows); n = len(rows)
    s["llm_share"] = round(sum(r["path"] in ("opus", "fable") for r in rows) / n, 3)
    s["not_run"] = sum(r["path"].endswith("NOT_RUN") for r in rows)
    s["usd_per_10k"] = round(sum(r["cost"] for r in rows) / n * 1e4)
    s["errors"] = [(r["id"], r["exc"], r["gold"], r["pred"], r["path"]) for r in rows if r["pred"] != r["gold"]]
    return s

CASES = {
    "A v2_par(기존)": {},
    "B1 의심하한 0.020": dict(t_lo=0.020),
    "B2 의심하한 0.015": dict(t_lo=0.015),
    "B3 의심하한 0.010": dict(t_lo=0.010),
    "B4 하한0.015+상한0.035": dict(t_lo=0.015, t_hi=0.035),
    "C v3 얼룩색 규칙": dict(stain=True),
    "D1 v3 + 밝기의심 제거": dict(stain=True, sus_db=False),
    "D2 v3 + 밝기의심 제거 + 확신0.5": dict(stain=True, sus_db=False, conf=0.5),
    "D3 v3 + 밝기의심 제거 + 확신0.7": dict(stain=True, sus_db=False, conf=0.7),
    "D4 v3 + 밝기의심·파손플래그 제거": dict(stain=True, sus_db=False, flag_dmg=False),
    "F1 v3 얼룩색+찢김색(밝기검사 대체)": dict(stain=True, hole=True, sus_db=False),
    "F2 F1 + 확신0.5": dict(stain=True, hole=True, sus_db=False, conf=0.5),
    "F3 F1 + 확신0.7": dict(stain=True, hole=True, sus_db=False, conf=0.7),
    "F4 F1 + 파손플래그 제거": dict(stain=True, hole=True, sus_db=False, flag_dmg=False),
    "F5 F4 + 확신0.5": dict(stain=True, hole=True, sus_db=False, flag_dmg=False, conf=0.5),
    "E1 v2 + 넘어간 건 Fable": dict(esc="fable"),
    "E2 F4 + Fable": dict(stain=True, hole=True, sus_db=False, flag_dmg=False, esc="fable"),
}
if __name__ == "__main__":
    res = {}
    for s in ("stream", "hard"):
        res[s] = {k: summ(run(s, **kw)) for k, kw in CASES.items()}
    json.dump(res, open(os.path.join(ROOT, "results", "v3_eval.json"), "w"), indent=1, ensure_ascii=False)
    for s in ("stream", "hard"):
        print(f"\n== {s}")
        for k, v in res[s].items():
            print(f"{k:34s} ok {v['correct']:3d}/{v['n']} dmg {v['dmg_caught']:6s} exc {v['exc_correct']:6s} FR {v['false_reject']} llm {v['llm_share']:.2f} NR {v['not_run']:2d} mean {v['t_mean']:.2f} p50 {v['t_p50']:.2f} p95 {v['t_p95']:.2f} $10k {v['usd_per_10k']}")
    for s in ("stream", "hard"):
        for k in ("A v2_par(기존)", "C v3 얼룩색 규칙", "F1 v3 얼룩색+찢김색(밝기검사 대체)", "F4 F1 + 파손플래그 제거", "F5 F4 + 확신0.5"): print(s, k, res[s][k]["errors"])
