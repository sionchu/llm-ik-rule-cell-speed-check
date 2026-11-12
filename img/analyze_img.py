"""Tables for the Isaac image sorting cell: accuracy and decision time per method, gate (rule+vision first, LLM only when the
barcode is not decoded or the rule fell through), and a throughput / recirculation model.
Timing model ASSUMPTIONS (not measured): sorter loop time LOOP_S, decision deadline = time for the tray to reach its chute
(uniform 5..LOOP_S-5 s after induct), person video coding 15 s/parcel (BEUMER figure)."""
import json, os, sys, random, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
LOOP_S = float(os.environ.get("LOOP_S", 60)); HUMAN_S = 15.0
cyc = json.load(open(os.path.join(ROOT, "results", "robot_cycle.json")))
CYCLE_CELL = cyc["parcel_h_0.25"]["induct"]["cycle_s"]; CYCLE_IND = 2.0      # this RB16 cell vs industry induction robot (~1,800 PPH)
EXC = {"RESCAN", "MANUAL", "REJECT"}

def rd(p): return {j["id"]: j for j in map(json.loads, open(p, encoding="utf-8"))} if os.path.exists(p) else {}
sets = {s: [json.loads(l) for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8")] for s in ("stream", "hard")}
methods = {"rule_vision": "룰+비전 (바코드→OCR→규칙)"}
for p in sorted(glob.glob(os.path.join(HERE, "pred_*_hard.jsonl")) + glob.glob(os.path.join(HERE, "pred_*_stream.jsonl"))):
    k = os.path.basename(p)[5:].rsplit("_", 1)[0]
    if k != "rule_vision": methods.setdefault(k, k)

def load(m, s):
    d = rd(os.path.join(HERE, f"pred_{m}_{s}.jsonl"))
    return {k: v for k, v in d.items() if v.get("status", "SUCCESS") == "SUCCESS" and v.get("pred")} if m != "rule_vision" else d

def outcome(pred, gold):
    if pred == gold: return "ok"
    if gold not in EXC and pred in EXC: return "to_person"        # safe but needs a person (video coding)
    return "wrong"                                               # missort or missed exception

def stats(ids, P, gold, lat):
    o = [outcome(P[i], gold[i]) for i in ids]; n = len(ids)
    L = np.array([lat[i] for i in ids])
    return dict(n=n, ok=o.count("ok"), to_person=o.count("to_person"), wrong=o.count("wrong"),
                lat_med=float(np.median(L)), lat_mean=float(L.mean()), lat_p90=float(np.percentile(L, 90)))

def recirc(L, seed=0):
    r = random.Random(seed); dl = np.array([r.uniform(5, LOOP_S - 5) for _ in L])
    return float(np.mean(np.asarray(L) > dl))

lines = [f"# Isaac 소포 분류 셀 결과\n", f"로봇 사이클(이 셀, RB16 코봇 가정 속도): {CYCLE_CELL:.2f} s → {3600/CYCLE_CELL:.0f}개/h. 업계 인덕션 로봇 가정 2.0 s → 1,800개/h.",
         f"순환 모델 가정: 소터 한 바퀴 {LOOP_S:.0f} s, 판단 마감 = 트레이가 슈트에 닿는 시간(5~{LOOP_S-5:.0f} s 균등), 사람 비디오 코딩 15 s/건.\n"]
for s, rows in sets.items():
    gold = {z["id"]: z["action"] for z in rows}
    rv = load("rule_vision", s)
    lines += [f"\n## {s} ({len(rows)}건, 예외 {sum(z['action'] in EXC for z in rows)}건)\n",
              "| 방식 | 범위 | 정답 | 사람에게 넘김(불필요) | 오분류·예외 놓침 | 판단 시간 중앙 / 평균 / p90 | LLM 호출 비율 | 순환 발생 |", "|---|---|---|---|---|---|---|---|"]
    for m in methods:
        P = load(m, s)
        ids = [z["id"] for z in rows if z["id"] in P]
        if len(ids) < 0.9 * len(rows): continue
        st = stats(ids, {i: P[i]["pred"] for i in ids}, gold, {i: P[i]["latency_s"] for i in ids})
        lines.append(f"| {methods[m]} | {st['n']} | {st['ok']} | {st['to_person']} | {st['wrong']} | {st['lat_med']:.2f} / {st['lat_mean']:.2f} / {st['lat_p90']:.2f} s | {'0%' if m=='rule_vision' else '100%'} | {recirc([P[i]['latency_s'] for i in ids]):.0%} |")
    # gate: rule+vision decides when the barcode decoded (hard evidence) or a physical check fired; otherwise the LLM
    for m in methods:
        if m == "rule_vision": continue
        P = load(m, s)
        ids = [z["id"] for z in rows if z["id"] in rv]
        defer = [i for i in ids if not rv[i]["evidence"].get("barcode") and rv[i]["pred"] not in ("REJECT",) and not (rv[i]["pred"] == "MANUAL" and rv[i]["evidence"].get("red", 0) > 0.0015)]
        if any(i not in P for i in defer): continue
        pred = {i: (P[i]["pred"] if i in defer else rv[i]["pred"]) for i in ids}
        # time: barcode/check stages always run; deferred parcels add the LLM call instead of OCR
        lat = {i: (rv[i]["stages"].get("barcode_s", 0) + rv[i]["stages"].get("checks_s", 0) + (P[i]["latency_s"] if i in defer else 0)) for i in ids}
        st = stats(ids, pred, gold, lat)
        lines.append(f"| 게이트: 룰+비전 → {methods[m]} | {st['n']} | {st['ok']} | {st['to_person']} | {st['wrong']} | {st['lat_med']:.2f} / {st['lat_mean']:.2f} / {st['lat_p90']:.2f} s | {len(defer)/len(ids):.0%} | {recirc(list(lat.values())):.0%} |")
open(os.path.join(ROOT, "RESULTS_isaac.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n"); print("\n".join(lines))
