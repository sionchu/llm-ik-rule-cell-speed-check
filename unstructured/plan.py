r"""Candidate generation: Lula IK + collision check for every (grasp point x wrist flip x transfer height). Run with C:\isaacsim\python.bat
(no SimulationApp, no GPU). Also evaluates the taught rule path (no collision check, as a taught program would run).
Output: cands.jsonl (one line per scene)."""
import json, math, os, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, os.environ.get("CELLKIT_DIR", "cellkit"))   # RB16 FK/IK + collision helper from a separate cell project, not included
import cellkit as ck
from common_u import *

ck.CFG["tools"] = {"S": {"length": 0.16, "radius": 0.04, "bit_length": 0.02, "depth": 0.0, "process_s": 0.0}}
ck.CFG["robot"]["joint_vel_max"] = 2.0; ck.CFG["robot"]["joint_acc_max"] = 6.0     # same as the parcel cell (assumption)
kin = ck.Kin(); col = ck.Collider(kin, n_per_link=250)
HOME_Q = np.array([-1.5708, 0.0, 1.5708, 0.0, 1.5708, 0.0])
A = ck._aabb
BASE_OBS = [A("pedestal", [-0.20, -0.20, 0.00, 0.20, 0.20, 0.75], "base"), A("floor", [-5, -5, -1, 5, 5, 0.0], "floor"),
            A("belt", [-1.2, BELT_Y - BELT_HALF, 0.0, 1.2, BELT_Y + BELT_HALF, BELT_TOP - 0.02]),
            A("rail_a", [-1.2, BELT_Y - BELT_HALF - 0.03, BELT_TOP, 1.2, BELT_Y - BELT_HALF, BELT_TOP + 0.10]),
            A("rail_b", [-1.2, BELT_Y + BELT_HALF, BELT_TOP, 1.2, BELT_Y + BELT_HALF + 0.03, BELT_TOP + 0.10])]
for k, p in enumerate(destinations()):     # funnel walls (4 thin plates per drop point)
    h = FUNNEL / 2
    for n, (x0, y0, x1, y1) in enumerate(((-h, -h, h, -h + 0.01), (-h, h - 0.01, h, h), (-h, -h, -h + 0.01, h), (h - 0.01, -h, h, h))):
        BASE_OBS.append(A(f"f{k}_{n}", [p[0] + x0, p[1] + y0, 0.45, p[0] + x1, p[1] + y1, SEP_TOP]))

def tip_pose(xy, z, yaw):
    return ck.tool_tip_pose(np.array([xy[0], xy[1], z]), [0, 0, -1], 0, ref=[math.cos(yaw), math.sin(yaw), 0])

def ik(xy, z, yaw, seed):
    s = kin.ik_tip(tip_pose(xy, z, yaw), "S", [seed, HOME_Q])
    return None if s is None else s[0]

def box_pts(b, g):
    """Carried-box surface samples in the tool-tip frame (tip z points down into the box; tip x = box long axis)."""
    us = np.linspace(-b["L"] / 2, b["L"] / 2, 6) - g[0]; vs = np.linspace(-b["W"] / 2, b["W"] / 2, 5) - g[1]; ws = np.linspace(0.01, b["H"], 4)
    return np.array([[u, v, w] for u in us for v in vs for w in ws if u in (us[0], us[-1]) or v in (vs[0], vs[-1]) or w == ws[-1]])

def seg_hits(qa, qb, obs, carry=None, n=8):
    col.obbs = obs; m = ck.CFG["check"]["collision_margin"]
    for t in np.linspace(0, 1, n):
        q = qa + (qb - qa) * t
        h = col.hits(q, "S")
        if h: return h
        if carry is not None:
            T = kin.tip(q, "S"); P = carry @ T[:3, :3].T + T[:3, 3]
            for ob in obs:
                loc = (P - ob["c"]) @ ob["R"]
                if np.all(np.abs(loc) <= np.asarray(ob["h"]) + m, axis=1).any(): return [f"box:{ob['name']}"]
    return []

def plan(b, g, flip, transfer, check=True):
    gw = box_to_world(b, g); yaw_p = b["yaw"] + (math.pi if flip else 0.0)
    dest = destinations()[b["dest"]]; yaw_d = math.atan2(dest[1], dest[0]) + (math.pi if flip else 0.0)   # box long axis radial in the funnel
    top = BELT_TOP + b["H"]
    zt = {"low": top + 0.05, "mid": 1.05, "high": TRANSFER_TAUGHT}[transfer] if isinstance(transfer, str) else transfer
    zt = max(zt, top + 0.05); zdrop = SEP_TOP + DROP_CLEAR + b["H"]
    obs = list(BASE_OBS)
    if b["neighbor"]:
        n = b["neighbor"]; obs.append(A("neighbor", [n["x"] - n["L"] / 2, n["y"] - n["W"] / 2, BELT_TOP, n["x"] + n["L"] / 2, n["y"] + n["W"] / 2, BELT_TOP + n["H"]]))
    q_home = ik(HOME_TIP[:2], HOME_TIP[2], -math.pi / 2, HOME_Q)
    q_pre = ik(gw, top + 0.10, yaw_p, q_home); q_pick = ik(gw, top, yaw_p, q_pre) if q_pre is not None else None
    q_lift = ik(gw, zt, yaw_p, q_pick) if q_pick is not None else None
    q_over = ik(dest, max(zt, zdrop), yaw_d, q_lift) if q_lift is not None else None
    q_drop = ik(dest, zdrop, yaw_d, q_over) if q_over is not None else None
    seq = [q_home, q_pre, q_pick, q_lift, q_over, q_drop, q_over, q_home]
    if any(q is None for q in seq): return dict(ik=False)
    mv = [ck.move_time(a, c) for a, c in zip(seq[:-1], seq[1:])]
    out = dict(ik=True, move_s=round(sum(mv) + 2 * VAC_S, 3), z_transfer=round(zt, 3))
    if check:
        carry = box_pts(b, g); hit = []
        for i, (qa, qc) in enumerate(zip(seq[:-1], seq[1:])):
            hit = seg_hits(qa, qc, obs, carry if 2 <= i <= 4 else None)
            if hit: out["hit"] = hit[:2]; out["hit_seg"] = i; break
        out["collision_free"] = not hit
    return out

if __name__ == "__main__":
    rows = [json.loads(l) for l in open(HERE / "scenes.jsonl")]
    with open(HERE / "cands.jsonl", "w") as f:
        for b in rows:
            t0 = time.perf_counter(); cands = []
            for gi, g in enumerate(grasp_points(b)):
                for flip in (0, 1):
                    for tr in TRANSFER_OPTS:
                        c = dict(cid=f"g{gi}{'f' if flip else 'n'}{tr[0]}", grasp=gi, flip=flip, transfer=tr, geom_ok=geom_ok(b, g), damage_ok=damage_ok(b, g))
                        if c["geom_ok"]: c.update(plan(b, g, flip, tr))   # geometric reject first (no IK needed)
                        else: c.update(ik=None)
                        cands.append(c)
            t_cand = time.perf_counter() - t0
            # taught rule: centre grasp, wrist convention with |tool yaw| <= 90 deg, taught transfer height, no collision check while running
            yaw_n = (b["yaw"] + math.pi / 2) % math.pi - math.pi / 2; flip_r = 0 if abs(yaw_n - b["yaw"]) < 1e-6 else 1
            t1 = time.perf_counter(); rule = plan(b, (0.0, 0.0), flip_r, TRANSFER_TAUGHT, check=False); t_rule = time.perf_counter() - t1
            rule_actual = plan(b, (0.0, 0.0), flip_r, TRANSFER_TAUGHT, check=True)   # what actually happens (collision = crash)
            rule.update(collision_free=rule_actual.get("collision_free"), hit=rule_actual.get("hit"), geom_ok=geom_ok(b, (0, 0)), damage_ok=damage_ok(b, (0, 0)))
            f.write(json.dumps(dict(id=b["id"], cands=cands, rule=rule, t_cand_s=round(t_cand, 2), t_rule_s=round(t_rule, 3))) + "\n"); f.flush()
            ok = sum(bool(c.get("collision_free")) and c["geom_ok"] for c in cands)
            print(b["id"], b["kind"], "valid", ok, "/", len(cands), "rule", rule.get("ik"), rule.get("collision_free"), round(t_cand, 1), "s", flush=True)
