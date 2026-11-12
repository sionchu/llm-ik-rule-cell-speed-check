"""Compare taught rule / geometric rule / LLM choice / oracle on the unstructured set. -> results_u.json + printed table"""
import json, os, statistics as st, sys
from collections import Counter
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = sys.argv[1] if len(sys.argv) > 1 else "claude_claude-opus-5-5-low"
sc = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(HERE, "scenes.jsonl"))}
cd = [json.loads(l) for l in open(os.path.join(HERE, "cands.jsonl"))]
pr = {json.loads(l)["id"]: json.loads(l) for l in open(os.path.join(HERE, f"pred_{MODEL}.jsonl"))} if os.path.exists(os.path.join(HERE, f"pred_{MODEL}.jsonl")) else {}
def valid(c): return c.get("collision_free") and c["geom_ok"]
def fastest(cs): return min(cs, key=lambda c: (c["move_s"], c["grasp"] != 0)) if cs else None

R = {k: [] for k in ("rule_taught", "rule_geom", "llm", "oracle")}
for d in cd:
    b = sc[d["id"]]; vs = [c for c in d["cands"] if valid(c)]
    r = d["rule"]
    fail = None if not r.get("ik") else "crash" if not r.get("collision_free") else "drop" if not (r["geom_ok"] and r["damage_ok"]) else None
    if not r.get("ik"): fail = "no_ik"
    R["rule_taught"].append(dict(id=b["id"], kind=b["kind"], ok=fail is None, fail=fail, judge_s=d["t_rule_s"], move_s=r.get("move_s")))
    g = fastest(vs)
    R["rule_geom"].append(dict(id=b["id"], kind=b["kind"], ok=bool(g and g["damage_ok"]), fail=None if g and g["damage_ok"] else ("no_cand" if not g else "drop"),
                               judge_s=d["t_cand_s"], move_s=g and g["move_s"]))
    p = pr.get(b["id"]); grasps = {c["grasp"] for c in vs}
    if len(grasps) < 2: c, js, src = g, d["t_cand_s"], "no_choice"
    elif p and p.get("status") == "SUCCESS":
        c = next((x for x in vs if x["cid"] == p["cid"]), None); js = d["t_cand_s"] + (p.get("api_ms") or p["latency_s"] * 1000) / 1000; src = "llm"
    else: c, js, src = g, d["t_cand_s"], "llm_NOT_RUN"
    R["llm"].append(dict(id=b["id"], kind=b["kind"], ok=bool(c and c["damage_ok"]), fail=None if c and c["damage_ok"] else ("no_cand" if not vs else "invalid_cid" if c is None else "drop"),
                         judge_s=js, move_s=c and c["move_s"], src=src, cost=(p or {}).get("cost_usd_list") if src == "llm" else 0))
    o = fastest([x for x in vs if x["damage_ok"]])
    R["oracle"].append(dict(id=b["id"], kind=b["kind"], ok=o is not None, fail=None if o else "no_cand", judge_s=d["t_cand_s"], move_s=o and o["move_s"]))

def summ(rows):
    n = len(rows); ok = [r for r in rows if r["ok"]]
    s = dict(n=n, success=len(ok), fails=dict(Counter(r["fail"] for r in rows if r["fail"])),
             judge_mean=round(st.mean(r["judge_s"] for r in rows), 2), move_mean_ok=round(st.mean(r["move_s"] for r in ok), 2) if ok else None,
             by_kind={k: f'{sum(r["ok"] for r in rows if r["kind"]==k)}/{sum(r["kind"]==k for r in rows)}' for k in ("none", "torn", "wet", "both")})
    if ok: s["cycle_ok_mean"] = round(st.mean(r["judge_s"] + r["move_s"] for r in ok), 2)
    if "src" in rows[0]: s["src"] = dict(Counter(r["src"] for r in rows)); s["llm_cost_usd_cli"] = round(sum(r["cost"] or 0 for r in rows), 3)
    return s
res = {k: summ(v) for k, v in R.items()}
json.dump(dict(summary=res, rows=R), open(os.path.join(HERE, "results_u.json"), "w"), indent=1)
for k, v in res.items(): print(k, json.dumps(v, ensure_ascii=False))
