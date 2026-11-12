"""Unstructured pick-and-place cell (2026-11-12): shared layout + suction model. Units m, kg, rad. World Z up, robot base (0,0,0.75).
All layout numbers are modelling ASSUMPTIONS for a comparison, not a real cell."""
import math
import numpy as np

BELT_TOP = 0.62; BELT_Y = -0.62; BELT_HALF = 0.30          # infeed belt along X
HOME_TIP = np.array([0.0, -0.40, 1.20])                      # taught home, tool down
SEP_TOP = 0.80                                              # funnel wall top
FUNNEL = 0.22                                               # funnel opening (square)
DROP_CLEAR = 0.05                                           # box bottom this far above funnel walls at release
TRANSFER_TAUGHT = 1.20                                      # rule: taught transfer height (tool tip z)
TRANSFER_OPTS = ("low", "mid", "high")                      # candidates: low = box top + 0.05 (no lift), mid = 1.05, high = 1.20
CUP_R = 0.045; FACE_INSET = 0.01; TORQUE_MAX = 15.0          # suction: cup radius, edge inset, max holding torque N*m (ASSUMPTION)
VAC_S = 0.15

def destinations():
    d = []
    for r, angs in ((0.50, (30, 60, 90, 120, 150)), (0.68, (20, 40, 60, 80, 100, 120, 140, 160)), (0.82, (75, 105))):
        for a in angs: d.append(np.array([r * math.cos(math.radians(a)), r * math.sin(math.radians(a))]))
    return d   # 15 drop points (12 chutes + RESCAN + MANUAL + REJECT)

def grasp_points(b):
    """9 candidate suction points in the box frame (x = long axis): centre + 3x3 grid at +-0.3 L / +-0.3 W, pulled in so the cup stays on the face."""
    L, W = b["L"], b["W"]
    a = max(0.0, min(0.3 * L, L / 2 - CUP_R - FACE_INSET - 0.005)); c = max(0.0, min(0.3 * W, W / 2 - CUP_R - FACE_INSET - 0.005))  # stay on the face
    return [(0.0, 0.0)] + [(u * a, v * c) for u in (-1, 0, 1) for v in (-1, 0, 1) if (u, v) != (0, 0)]

def geom_ok(b, g):
    """Geometric suction check a vision+rule system can do (box size + scale reading): cup inside the face, torque."""
    gx, gy = g
    inside = abs(gx) + CUP_R + FACE_INSET <= b["L"] / 2 and abs(gy) + CUP_R + FACE_INSET <= b["W"] / 2
    torque = b["mass"] * 9.81 * math.hypot(gx, gy)
    return inside and torque <= TORQUE_MAX

def damage_ok(b, g):
    """Ground truth: the cup must not touch a torn hole or a wet patch (suction leaks / carton tears)."""
    return all(math.hypot(g[0] - d["x"], g[1] - d["y"]) > d["r"] + CUP_R for d in b["damage"])

def box_to_world(b, p):
    c, s = math.cos(b["yaw"]), math.sin(b["yaw"])
    return np.array([b["x"] + c * p[0] - s * p[1], b["y"] + s * p[0] + c * p[1]])
