"""Isaac Sim front-view clips for the unstructured cell (2026-11-12): one box, three ways to pick it.
    C:\\isaacsim\\python.bat isaac\\unstruct_video.py u_006
rule  = taught centre grasp + taught transfer height (no run-time collision check)  -> crash where plan.py found a hit
geom  = fastest IK + collision-valid candidate (image not used)                     -> drop if the cup is on damage
llm   = candidate Opus chose                                                        -> placed in the funnel
Kinematic only (same cellkit timing as plan.py). Frames -> results/video_u/<id>_<mode>/NNNN.png, meta -> results/video_u/meta.json"""
import json, math, sys, os
from pathlib import Path
import numpy as np
from isaacsim import SimulationApp
SID = sys.argv[1] if len(sys.argv) > 1 else "u_006"
SUB = int(os.environ.get("SUB", "8"))
HERE = Path(__file__).resolve().parents[1]; U = HERE / "unstructured"
app = SimulationApp({"headless": True, "width": 1280, "height": 720, "renderer": "RaytracedLighting"})
import carb.settings  # noqa
cs = carb.settings.get_settings(); cs.set("/rtx/post/aa/op", 2); cs.set("/rtx/post/dlss/execMode", 0); cs.set("/rtx/post/motionblur/enabled", False)
import imageio.v2 as imageio  # noqa
import omni.replicator.core as rep  # noqa
import omni.usd  # noqa
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade, Vt  # noqa
from PIL import Image, ImageDraw  # noqa
sys.path.insert(0, str(U))
import plan as PL  # noqa  (loads cellkit, kin, collider, obstacles, suction tool)
from common_u import *  # noqa
ck = PL.ck; kin = PL.kin
FPS = 24

omni.usd.get_context().new_stage(); stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
_m = {}
def mat(name, rgb, rough=0.6, metal=0.0, tex=None):
    key = name if tex is None else str(tex)
    if key in _m: return _m[key]
    path = f"/World/Looks/M{len(_m)}"
    m = UsdShade.Material.Define(stage, path); s = UsdShade.Shader.Define(stage, path + "/S"); s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough); s.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
    if tex:
        rd = UsdShade.Shader.Define(stage, path + "/st"); rd.CreateIdAttr("UsdPrimvarReader_float2"); rd.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        t = UsdShade.Shader.Define(stage, path + "/tex"); t.CreateIdAttr("UsdUVTexture"); t.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(tex))
        t.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(rd.ConnectableAPI(), "result"); t.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(t.ConnectableAPI(), "rgb")
    else:
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface"); _m[key] = m; return m
def bind(p, m): UsdShade.MaterialBindingAPI.Apply(p.GetPrim()).Bind(m)
def set_T(prim, T):
    xf = UsdGeom.Xformable(prim); ops = xf.GetOrderedXformOps(); op = ops[0] if ops else xf.AddTransformOp()
    op.Set(Gf.Matrix4d(*np.asarray(T, float).T.flatten().tolist()))
def boxp(path, lo, hi, m):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float); x = UsdGeom.Xform.Define(stage, path); T = np.eye(4); T[:3, :3] = np.diag(hi - lo); T[:3, 3] = (lo + hi) / 2; set_T(x, T)
    cu = UsdGeom.Cube.Define(stage, path + "/b"); cu.CreateSizeAttr(1.0); bind(cu, m); return x
def look(eye, target, up=(0, 0, 1)):
    eye, target = np.asarray(eye, float), np.asarray(target, float); z = ck.unit(eye - target); x = ck.unit(np.cross(up, z))
    T = np.eye(4); T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = x, np.cross(z, x), z, eye; return T
def stl_mesh(path, stl, m):
    tris = ck._read_stl(stl); me = UsdGeom.Mesh.Define(stage, path)
    me.CreatePointsAttr([Gf.Vec3f(*p) for p in tris.reshape(-1, 3)]); me.CreateFaceVertexCountsAttr([3] * len(tris))
    me.CreateFaceVertexIndicesAttr(list(range(3 * len(tris)))); me.CreateSubdivisionSchemeAttr("none"); bind(me, m)

b = next(json.loads(l) for l in open(U / "scenes.jsonl") if json.loads(l)["id"] == SID)
cand = next(json.loads(l) for l in open(U / "cands.jsonl") if json.loads(l)["id"] == SID)
pred = next(json.loads(l) for l in open(U / "pred_claude_claude-opus-5-5-low.jsonl") if json.loads(l)["id"] == SID)
valid = sorted([c for c in cand["cands"] if c.get("collision_free") and c["geom_ok"]], key=lambda c: (c["move_s"], c["grasp"] != 0))
geo = valid[0]; llm = next(c for c in valid if c["cid"] == pred["cid"])

# ---- scene
UsdLux.DomeLight.Define(stage, "/World/Dome").CreateIntensityAttr(700)
sun = UsdLux.DistantLight.Define(stage, "/World/Sun"); sun.CreateIntensityAttr(2200); sun.CreateAngleAttr(1.5); set_T(sun, look((1.5, -2, 4), (0, 0, 0)))
boxp("/World/Floor", [-4, -4, -0.01], [4, 4, 0], mat("floor", (0.55, 0.56, 0.58), 0.85))
boxp("/World/Belt/frame", [-1.4, BELT_Y - BELT_HALF - 0.02, 0], [1.4, BELT_Y + BELT_HALF + 0.02, BELT_TOP - 0.02], mat("frame", (0.22, 0.30, 0.42), 0.5, 0.3))
boxp("/World/Belt/belt", [-1.4, BELT_Y - BELT_HALF, BELT_TOP - 0.02], [1.4, BELT_Y + BELT_HALF, BELT_TOP], mat("belt", (0.08, 0.08, 0.09), 0.9))
for nm, ob in (("rail_a", [-1.4, BELT_Y - BELT_HALF - 0.03, BELT_TOP, 1.4, BELT_Y - BELT_HALF, BELT_TOP + 0.10]), ("rail_b", [-1.4, BELT_Y + BELT_HALF, BELT_TOP, 1.4, BELT_Y + BELT_HALF + 0.03, BELT_TOP + 0.10])):
    boxp(f"/World/Belt/{nm}", ob[:3], ob[3:], mat("rail", (0.75, 0.6, 0.1), 0.4, 0.5))
boxp("/World/Pedestal", [-0.18, -0.18, 0], [0.18, 0.18, 0.75], mat("ped", (0.2, 0.22, 0.25), 0.5))
for k, p in enumerate(destinations()):
    h = FUNNEL / 2; col = mat("fhi", (0.15, 0.65, 0.35), 0.5) if k == b["dest"] else mat(f"f{k % 2}", (0.9, 0.55, 0.15) if k % 2 else (0.95, 0.75, 0.2), 0.5)
    for n, (x0, y0, x1, y1) in enumerate(((-h, -h, h, -h + 0.01), (-h, h - 0.01, h, h), (-h, -h, -h + 0.01, h), (h - 0.01, -h, h, h))):
        boxp(f"/World/Funnels/f{k:02d}_{n}", [p[0] + x0, p[1] + y0, 0.45], [p[0] + x1, p[1] + y1, SEP_TOP], col)
    boxp(f"/World/Funnels/f{k:02d}_post", [p[0] - 0.02, p[1] - 0.02, 0], [p[0] + 0.02, p[1] + 0.02, 0.45], mat("fp", (0.3, 0.3, 0.32), 0.4, 0.5))
if b["neighbor"]:
    n = b["neighbor"]; boxp("/World/Neighbor", [n["x"] - n["L"] / 2, n["y"] - n["W"] / 2, BELT_TOP], [n["x"] + n["L"] / 2, n["y"] + n["W"] / 2, BELT_TOP + n["H"]], mat("nb", (0.62, 0.48, 0.32), 0.8))
MESH = Path(os.environ.get("CELLKIT_DIR", "cellkit")).parent / "third_party/rbpodo_ros2/rbpodo_description/meshes/rb16_900e/collision"
links = {}
for ln in ["link0"] + ck.LINKS:
    x = UsdGeom.Xform.Define(stage, f"/World/RB16/{ln}")
    stl_mesh(f"/World/RB16/{ln}/mesh", MESH / f"{ln}.stl", mat("rb0", (0.2, 0.22, 0.25), 0.5) if ln == "link0" else mat("rb", (0.88, 0.89, 0.9), 0.4)); links[ln] = x
set_T(links["link0"], ck.base_T())
SUC = ck.CFG["tools"]["S"]["length"]
tool = UsdGeom.Xform.Define(stage, "/World/Suction")
c1 = UsdGeom.Cylinder.Define(stage, "/World/Suction/body"); c1.CreateRadiusAttr(0.03); c1.CreateHeightAttr(SUC - 0.03)
UsdGeom.Xformable(c1).AddTranslateOp().Set(Gf.Vec3d(0, 0, -(SUC + 0.03) / 2)); bind(c1, mat("tool", (0.25, 0.25, 0.28), 0.4, 0.6))
c2 = UsdGeom.Cylinder.Define(stage, "/World/Suction/cup"); c2.CreateRadiusAttr(CUP_R); c2.CreateHeightAttr(0.03)
UsdGeom.Xformable(c2).AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.015)); bind(c2, mat("cup", (0.1, 0.1, 0.1), 0.9))
def pose_robot(q):
    for ln in ck.LINKS: set_T(links[ln], kin.fk(q, ln))
    set_T(tool, kin.tip(q, "S"))

# box with a top texture (same drawing as the LLM image, no candidate marks)
TW, TH = 1024, int(1024 * b["W"] / b["L"])
im = Image.new("RGB", (TW, TH), (205, 165, 115)); d = ImageDraw.Draw(im)
def P(u, v): return ((u / b["L"] + 0.5) * TW, (0.5 - v / b["W"]) * TH)
d.rectangle([0, P(0, 0.025)[1], TW, P(0, -0.025)[1]], fill=(222, 205, 170))
lb = b["label"]; d.rectangle([*P(lb["x"] - 0.07, lb["y"] + 0.045), *P(lb["x"] + 0.07, lb["y"] - 0.045)], fill=(245, 245, 245), outline=(30, 30, 30))
for dm in b["damage"]:
    cx, cy = P(dm["x"], dm["y"]); rr = dm["r"] / b["L"] * TW
    if dm["kind"] == "torn":
        pts = [(cx + math.cos(a) * rr * (0.75 + 0.25 * math.sin(5 * a)), cy + math.sin(a) * rr * (0.75 + 0.25 * math.sin(5 * a))) for a in np.linspace(0, 2 * math.pi, 18)]
        d.polygon(pts, fill=(120, 106, 96))
    else: d.ellipse([cx - rr, cy - rr / 1.2, cx + rr, cy + rr / 1.2], fill=(150, 110, 75))
(HERE / "results" / "video_u").mkdir(parents=True, exist_ok=True); texp = HERE / "results" / "video_u" / f"{SID}_top.png"; im.save(texp)
parcel = UsdGeom.Xform.Define(stage, "/World/Box")
pb = UsdGeom.Cube.Define(stage, "/World/Box/body"); pb.CreateSizeAttr(1.0); bind(pb, mat("card", (0.73, 0.56, 0.36), 0.8))
me = UsdGeom.Mesh.Define(stage, "/World/Box/top")
me.CreatePointsAttr([Gf.Vec3f(-.5, -.5, .5005), Gf.Vec3f(.5, -.5, .5005), Gf.Vec3f(.5, .5, .5005), Gf.Vec3f(-.5, .5, .5005)])
me.CreateFaceVertexCountsAttr([4]); me.CreateFaceVertexIndicesAttr([0, 1, 2, 3]); me.CreateSubdivisionSchemeAttr("none")
UsdGeom.PrimvarsAPI(me).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex).Set(Vt.Vec2fArray([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)]))
bind(me, mat(None, None, 0.7, tex=texp))
def box_T(x, y, yaw, zc, tilt=0.0):
    c, s = math.cos(yaw), math.sin(yaw); Rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    ct, st = math.cos(tilt), math.sin(tilt); Rx = np.array([[1, 0, 0], [0, ct, -st], [0, st, ct]])
    T = np.eye(4); T[:3, :3] = Rz @ Rx @ np.diag([b["L"], b["W"], b["H"]]); T[:3, 3] = [x, y, zc]; return T
def sequence(g, flip, transfer):
    gw = box_to_world(b, g); yaw_p = b["yaw"] + (math.pi if flip else 0.0); dest = destinations()[b["dest"]]
    yaw_d = math.atan2(dest[1], dest[0]) + (math.pi if flip else 0.0); top = BELT_TOP + b["H"]
    zt = {"low": top + 0.05, "mid": 1.05, "high": TRANSFER_TAUGHT}[transfer] if isinstance(transfer, str) else transfer
    zt = max(zt, top + 0.05); zdrop = SEP_TOP + DROP_CLEAR + b["H"]
    q_home = PL.ik(HOME_TIP[:2], HOME_TIP[2], -math.pi / 2, PL.HOME_Q)
    q_pre = PL.ik(gw, top + 0.10, yaw_p, q_home); q_pick = PL.ik(gw, top, yaw_p, q_pre); q_lift = PL.ik(gw, zt, yaw_p, q_pick)
    q_over = PL.ik(dest, max(zt, zdrop), yaw_d, q_lift); q_drop = PL.ik(dest, zdrop, yaw_d, q_over)
    return [q_home, q_pre, q_pick, q_lift, q_over, q_drop, q_over, q_home]
yaw_n = (b["yaw"] + math.pi / 2) % math.pi - math.pi / 2; flip_r = 0 if abs(yaw_n - b["yaw"]) < 1e-6 else 1
gpts = grasp_points(b)
MODES = {"rule": ((0.0, 0.0), flip_r, TRANSFER_TAUGHT, "crash" if not cand["rule"].get("collision_free") else ("drop" if not cand["rule"]["damage_ok"] else "ok")),
         "geom": (gpts[geo["grasp"]], geo["flip"], geo["transfer"], "ok" if geo["damage_ok"] else "drop"),
         "llm": (gpts[llm["grasp"]], llm["flip"], llm["transfer"], "ok" if llm["damage_ok"] else "drop")}
obs = list(PL.BASE_OBS)
if b["neighbor"]:
    n = b["neighbor"]; obs.append(PL.A("neighbor", [n["x"] - n["L"] / 2, n["y"] - n["W"] / 2, BELT_TOP, n["x"] + n["L"] / 2, n["y"] + n["W"] / 2, BELT_TOP + n["H"]]))

for g in ("Neighbor",): pass
camera = UsdGeom.Camera.Define(stage, "/World/Front"); camera.CreateFocalLengthAttr(20.0); camera.CreateHorizontalApertureAttr(20.955)
camera.CreateVerticalApertureAttr(20.955 * 1080 / 1920); camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 30)); set_T(camera, look((0.6, -2.9, 2.2), (0.0, 0.05, 0.65)))
rp = rep.create.render_product("/World/Front", (1920, 1080)); ann = rep.AnnotatorRegistry.get_annotator("rgb"); ann.attach([rp]); rep.orchestrator.set_capture_on_play(False)
def ease(t): return t * t * (3 - 2 * t)
meta = {}
for mode, (g, flip, tr, outcome) in MODES.items():
    out = HERE / "results" / "video_u" / f"{SID}_{mode}"; out.mkdir(parents=True, exist_ok=True); nfr = [0]
    def shot():
        app.update(); rep.orchestrator.step(rt_subframes=SUB, delta_time=0.0, pause_timeline=False)
        imageio.imwrite(out / f"{nfr[0]:04d}.png", np.ascontiguousarray(ann.get_data()[:, :, :3])); nfr[0] += 1
    seq = sequence(g, flip, tr); zc0 = BELT_TOP + b["H"] / 2
    pose_robot(seq[0])
    for k in range(int(1.5 * FPS)):     # arrival along the belt
        x = -1.2 + (b["x"] + 1.2) * ease(k / (1.5 * FPS - 1)); set_T(parcel, box_T(x, b["y"], b["yaw"], zc0)); shot()
    n_arrive = nfr[0]; segs = []; rel = None; T_box = box_T(b["x"], b["y"], b["yaw"], zc0); event = None; ev_frame = None
    for j, (qa, qb) in enumerate(zip(seq[:-1], seq[1:])):
        dt = ck.move_time(qa, qb); m = max(2, int(round(dt * FPS))); segs.append(round(dt, 3))
        carry = PL.box_pts(b, g) if rel is not None else None
        for k in range(m):
            q = qa + (qb - qa) * ease((k + 1) / m)
            if mode == "rule" and outcome == "crash" and event is None:
                PL.col.obbs = obs; hit = PL.col.hits(q, "S")
                if not hit and carry is not None:
                    T = kin.tip(q, "S"); Pp = carry @ T[:3, :3].T + T[:3, 3]; mg = ck.CFG["check"]["collision_margin"]
                    hit = [ob["name"] for ob in obs if np.all(np.abs((Pp - ob["c"]) @ ob["R"]) <= np.asarray(ob["h"]) + mg, axis=1).any()]
                if hit: event = "crash"; ev_frame = nfr[0]
            pose_robot(q)
            if rel is not None: set_T(parcel, kin.tip(q, "S") @ rel)
            shot()
            if event == "crash": break
            if mode != "rule" or outcome == "drop":
                if outcome == "drop" and j == 3 and k == m // 2 and rel is not None:   # suction leaks on the damage: box slips off mid-lift
                    event = "drop"; ev_frame = nfr[0]; T0 = kin.tip(q, "S") @ rel; rel = None
                    for f in range(int(0.6 * FPS)):
                        a = (f + 1) / (0.6 * FPS); zc = T0[2, 3] + (zc0 - T0[2, 3]) * a * a
                        set_T(parcel, box_T(T0[0, 3], T0[1, 3], b["yaw"], zc, tilt=0.35 * a)); shot()
                    break
        if event: break
        if j == 1:                       # suction on at the pick pose
            rel = np.linalg.inv(kin.tip(qb, "S")) @ T_box
            for _ in range(int(VAC_S * FPS)): shot()
        if j == 4:                       # release over the funnel: box drops in
            T0 = kin.tip(qb, "S") @ rel; rel = None
            for f in range(int(0.4 * FPS)):
                a = (f + 1) / (0.4 * FPS); zc = T0[2, 3] - 0.30 * a * a; T1 = T0.copy(); T1[2, 3] = zc; set_T(parcel, T1); shot()
            UsdGeom.Imageable(stage.GetPrimAtPath("/World/Box")).MakeInvisible()
    for _ in range(int(0.8 * FPS)): shot()          # hold
    UsdGeom.Imageable(stage.GetPrimAtPath("/World/Box")).MakeVisible()
    meta[f"{SID}_{mode}"] = dict(frames=nfr[0], arrive_frames=n_arrive, outcome=outcome, event=event, event_frame=ev_frame, segments_s=segs,
                                 move_s=round(sum(segs) + 2 * VAC_S, 3), fps=FPS, cid=None if mode == "rule" else (geo if mode == "geom" else llm)["cid"])
    print(mode, meta[f"{SID}_{mode}"], flush=True)
mp = HERE / "results" / "video_u" / "meta.json"; old = json.loads(mp.read_text()) if mp.exists() else {}
old.update(meta); mp.write_text(json.dumps(old, indent=1))
app.close()
