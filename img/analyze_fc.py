"""FC outbound-check results (doc 28 sec. 8): first metric = missed faults (faulty parcel judged OK), cost $35 each;
an unneeded human check (OK parcel flagged) ~55 KRW. Real fault rate 0.1-0.5% -> table re-weighted to 0.3% per 10,000 parcels.
Gates: (A) LLM on every parcel, (B) rule first, LLM reviews only rule-flagged parcels, (C) rule first, LLM re-checks rule-OK parcels too
(= A in decisions, but shows the LLM share)."""
import json, os, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
USD = 1400; MISS_USD = 35.0; HUMAN_KRW = 55.0; RATE = 0.003


def rd(p):
    d = {}
    if os.path.exists(p):
        for j in map(json.loads, open(p, encoding="utf-8")):
            if j.get("status", "SUCCESS") == "SUCCESS" and j.get("pred"): d[j["id"]] = j
    return d


def score(ids, pred, gold):
    miss = sum(gold[i] != "OK" and pred[i] == "OK" for i in ids)
    fa = sum(gold[i] == "OK" and pred[i] != "OK" for i in ids)
    ok = sum(pred[i] == gold[i] for i in ids)
    wrongtype = sum(gold[i] != "OK" and pred[i] not in ("OK", gold[i]) for i in ids)
    nf = sum(gold[i] != "OK" for i in ids); nok = len(ids) - nf
    return dict(n=len(ids), ok=ok, miss=miss, fa=fa, wrongtype=wrongtype, nf=nf, nok=nok)


def per10k(st_f, st_ok):
    """missed-fault rate from the fault-heavy set, false-alarm rate from OK parcels of both sets -> 10,000 parcels at RATE."""
    mr = st_f["miss"] / max(1, st_f["nf"]); far = st_ok["fa"] / max(1, st_ok["nok"])
    faults = 10000 * RATE; miss = faults * mr; fa = (10000 - faults) * far
    return miss, fa, miss * MISS_USD * USD + fa * HUMAN_KRW


sets = {s: [json.loads(l) for l in open(os.path.join(HERE, "sets", f"{s}.jsonl"), encoding="utf-8")] for s in ("fc_stream", "fc_hard")}
gold = {z["id"]: z["action"] for rows in sets.values() for z in rows}
methods = {"rule_fc": "룰 (바코드 대조·무게 ±5%·색 검사·스티커 템플릿)"}
for p in glob.glob(os.path.join(HERE, "pred_*_roi_fc_*.jsonl")):
    k = os.path.basename(p)[5:].split("_roi_")[0] + "_roi"; methods.setdefault(k, k)
L = ["# FC 출고 검사 결과 (Isaac 셀, 쿠팡형 1차 범위: 라벨·파손·규격·포장)\n",
     f"놓친 오류 1건 = ${MISS_USD:.0f}(약 {MISS_USD*USD:,.0f}원), 불필요한 사람 확인 1건 = {HUMAN_KRW:.0f}원. 실제 오류율 {RATE*100:.1f}%로 1만 건당 환산.\n"]
res = {}
for m in methods:
    for s, rows in sets.items():
        P = rd(os.path.join(HERE, f"pred_{m}_{s}.jsonl")) if m == "rule_fc" else rd(os.path.join(HERE, f"pred_{m.replace('_roi','')}_roi_{s}.jsonl"))
        ids = [z["id"] for z in rows if z["id"] in P]
        if len(ids) < 0.9 * len(rows): continue
        res[(m, s)] = (score(ids, {i: P[i]["pred"] for i in ids}, gold), float(np.median([P[i]["latency_s"] for i in ids])), P)
for s in sets:
    L += [f"\n## {s}\n", "| 방식 | 건수 | 정답 | 놓친 오류(오류→OK) | 불필요 확인(OK→예외) | 예외 종류 틀림 | 판단 시간 중앙 |", "|---|---|---|---|---|---|---|"]
    for m in methods:
        if (m, s) in res:
            st, med, _ = res[(m, s)]
            L.append(f"| {methods[m]} | {st['n']} | {st['ok']} | {st['miss']} / {st['nf']} | {st['fa']} / {st['nok']} | {st['wrongtype']} | {med:.2f} s |")
L += ["\n## 1만 건당 환산 (오류율 0.3%: 오류 30건 + 정상 9,970건)\n", "| 방식 | 놓친 오류 | 불필요 확인 | 비용 합계 |", "|---|---|---|---|"]
for m in methods:
    if (m, "fc_hard") in res and (m, "fc_stream") in res:
        sh, ss = res[(m, "fc_hard")][0], res[(m, "fc_stream")][0]
        ok_pool = dict(fa=sh["fa"] + ss["fa"], nok=sh["nok"] + ss["nok"])
        miss, fa, cost = per10k(sh, ok_pool)
        L.append(f"| {methods[m]} | {miss:.1f}건 | {fa:.0f}건 | {cost:,.0f}원 |")
# gate B: rule flags -> LLM decides; rule OK stays OK
L += ["\n## 게이트 B: 룰이 예외라고 한 건만 LLM 재판정 (룰 OK는 그대로 출고)\n", "| LLM | 세트 | 놓친 오류 | 불필요 확인 | LLM 호출 비율 |", "|---|---|---|---|---|"]
for m in methods:
    if m == "rule_fc": continue
    for s in sets:
        if (m, s) not in res or ("rule_fc", s) not in res: continue
        R = res[("rule_fc", s)][2]; P = res[(m, s)][2]
        ids = [i for i in R if i in P]
        pred = {i: (P[i]["pred"] if R[i]["pred"] != "OK" else "OK") for i in ids}
        st = score(ids, pred, gold); share = sum(R[i]["pred"] != "OK" for i in ids) / len(ids)
        L.append(f"| {methods[m]} | {s} | {st['miss']} / {st['nf']} | {st['fa']} / {st['nok']} | {share:.0%} |")
open(os.path.join(ROOT, "RESULTS_fc.md"), "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L))
