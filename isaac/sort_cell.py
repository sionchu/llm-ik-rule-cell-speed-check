"""Isaac Sim 6.0.1 parcel induction / sorting cell (kinematic, RTX render). 2026-11-11.

Cell: infeed conveyor -> overhead camera at the pick point -> RB16-900E with a suction tool picks the parcel ->
places it on the induct of a loop sorter (12 destination chutes) or into the exception tote (REJECT / MANUAL).
Robot motion is kinematic (Lula IK + trapezoid joint timing, same model as our drill-cell study); there is no physics.

    C:\\isaacsim\\python.bat isaac\\sort_cell.py --capture            # camera image per parcel -> cam/<id>.png
    C:\\isaacsim\\python.bat isaac\\sort_cell.py --cycle              # robot cycle times -> results/robot_cycle.json
    C:\\isaacsim\\python.bat isaac\\sort_cell.py --stills             # overview stills -> results/media/
"""
import argparse, json, math, os, sys, time
from pathlib import Path
import numpy as np
from isaacsim import SimulationApp

ap = argparse.ArgumentParser()
ap.add_argument("--capture", action="store_true")
ap.add_argument("--cycle", action="store_true")
ap.add_argument("--stills", action="store_true")
ap.add_argument("--sets", nargs="*", default=["stream", "hard"])
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--video", nargs="*", default=[])   # id:dest pairs (dest = induct | tote), front-view frames
ap.add_argument("--sub", type=int, default=8)
ap.add_argument("--ids", default="")   # file of ids to re-capture (placement RNG still advanced for every row)
args = ap.parse_args()

HERE = Path(__file__).resolve().parents[1]
CELLKIT = Path(os.environ.get("CELLKIT_DIR", "cellkit"))   # kinematics helper (RB16 FK/IK, move timing) from a separate cell project, not included
app = SimulationApp({"headless": True, "width": 1280, "height": 720, "renderer": "RaytracedLighting"})
import carb.settings  # noqa: E402
cs = carb.settings.get_settings(); cs.set("/rtx/post/aa/op", 2); cs.set("/rtx/post/dlss/execMode", 0); cs.set("/rtx/post/motionblur/enabled", False)
import imageio.v2 as imageio  # noqa: E402
import omni.replicator.core as rep  # noqa: E402
import omni.usd  # noqa: E402
from pxr import Gf, Sdf, UsdGeom, UsdLux, UsdShade, Vt  # noqa: E402
sys.path.insert(0, str(CELLKIT))
import cellkit as ck  # noqa: E402

# ---- cell layout (assumptions, metres). Robot base from the drill-cell config: (0, 0, 0.75)
CONV_Y, CONV_TOP = -0.62, 0.62           # infeed conveyor centre line (along X) and belt height
PICK_XY = np.array([0.0, CONV_Y])         # pick point = under the camera
INDUCT = np.array([0.0, 0.62, 0.70])      # sorter induct point (other side of the robot)
TOTE = np.array([0.58, 0.0, 0.55])        # exception tote (REJECT / MANUAL)
CAM_H = 1.10                              # camera height above the belt
SUCTION = 0.16                            # suction tool length (flange -> cup)
ck.CFG["tools"]["S"] = {"length": SUCTION, "radius": 0.04, "bit_length": 0.02, "depth": 0.0, "process_s": 0.0}
ck.CFG["robot"]["joint_vel_max"] = 2.0    # rad/s ASSUMPTION for sorting duty (drill cell used 1.0)
ck.CFG["robot"]["joint_acc_max"] = 6.0    # rad/s^2 ASSUMPTION
VAC_S = 0.15                              # suction on / off each (assumption)

omni.usd.get_context().new_stage(); stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
_m = {}

def mat(name, rgb, rough=0.6, metal=0.0, tex=None):
    key = name if tex is None else tex
    if key in _m: return _m[key]
    path = f"/World/Looks/M{len(_m)}"
    m = UsdShade.Material.Define(stage, path); s = UsdShade.Shader.Define(stage, path + "/S"); s.CreateIdAttr("UsdPreviewSurface")
    s.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough); s.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
    if tex:
        rd = UsdShade.Shader.Define(stage, path + "/st"); rd.CreateIdAttr("UsdPrimvarReader_float2")
        rd.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        t = UsdShade.Shader.Define(stage, path + "/tex"); t.CreateIdAttr("UsdUVTexture")
        t.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(tex))
        t.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(rd.ConnectableAPI(), "result")
        t.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(t.ConnectableAPI(), "rgb")
    else:
        s.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    m.CreateSurfaceOutput().ConnectToSource(s.ConnectableAPI(), "surface"); _m[key] = m
    return m

def bind(p, m): UsdShade.MaterialBindingAPI.Apply(p.GetPrim()).Bind(m)

def set_T(prim, T):
    xf = UsdGeom.Xformable(prim); ops = xf.GetOrderedXformOps(); op = ops[0] if ops else xf.AddTransformOp()
    op.Set(Gf.Matrix4d(*np.asarray(T, float).T.flatten().tolist()))

def box(path, c, h, m):
    x = UsdGeom.Xform.Define(stage, path); T = np.eye(4); T[:3, :3] = np.diag(2 * np.asarray(h, float)); T[:3, 3] = c; set_T(x, T)
    cu = UsdGeom.Cube.Define(stage, path + "/b"); cu.CreateSizeAttr(1.0); bind(cu, m); return x

def quad(path, c, sx, sy, m, yaw=0.0):
    me = UsdGeom.Mesh.Define(stage, path)
    me.CreatePointsAttr([Gf.Vec3f(-.5, -.5, 0), Gf.Vec3f(.5, -.5, 0), Gf.Vec3f(.5, .5, 0), Gf.Vec3f(-.5, .5, 0)])
    me.CreateFaceVertexCountsAttr([4]); me.CreateFaceVertexIndicesAttr([0, 1, 2, 3]); me.CreateSubdivisionSchemeAttr("none")
    pv = UsdGeom.PrimvarsAPI(me).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
    pv.Set(Vt.Vec2fArray([Gf.Vec2f(0, 0), Gf.Vec2f(1, 0), Gf.Vec2f(1, 1), Gf.Vec2f(0, 1)]))
    T = np.eye(4); cz, sz = math.cos(yaw), math.sin(yaw); T[:3, :3] = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.diag([sx, sy, 1]); T[:3, 3] = c
    set_T(me, T); bind(me, m); return me

def look(eye, target, up=(0, 0, 1)):
    eye, target = np.asarray(eye, float), np.asarray(target, float); z = ck.unit(eye - target); x = ck.unit(np.cross(up, z))
    T = np.eye(4); T[:3, 0], T[:3, 1], T[:3, 2], T[:3, 3] = x, np.cross(z, x), z, eye; return T

def stl_mesh(path, stl, m):
    tris = ck._read_stl(stl); me = UsdGeom.Mesh.Define(stage, path)
    me.CreatePointsAttr([Gf.Vec3f(*p) for p in tris.reshape(-1, 3)]); me.CreateFaceVertexCountsAttr([3] * len(tris))
    me.CreateFaceVertexIndicesAttr(list(range(3 * len(tris)))); me.CreateSubdivisionSchemeAttr("none"); bind(me, m)

# ---- static scene
UsdLux.DomeLight.Define(stage, "/World/Dome").CreateIntensityAttr(700)
sun = UsdLux.DistantLight.Define(stage, "/World/Sun"); sun.CreateIntensityAttr(2200); sun.CreateAngleAttr(1.5); set_T(sun, look((1.5, -2, 4), (0, 0, 0)))
lamp = UsdLux.RectLight.Define(stage, "/World/CamLight"); lamp.CreateIntensityAttr(9000); lamp.CreateWidthAttr(0.6); lamp.CreateHeightAttr(0.6)
set_T(lamp, look((PICK_XY[0] + 0.25, PICK_XY[1], CONV_TOP + 1.3), (PICK_XY[0], PICK_XY[1], CONV_TOP)))
box("/World/Floor", [0, 0, -0.005], [4, 4, 0.005], mat("floor", (0.55, 0.56, 0.58), 0.85))
# infeed conveyor (frame + belt + rollers hint)
box("/World/Infeed/frame", [0, CONV_Y, CONV_TOP / 2 - 0.02], [1.6, 0.36, CONV_TOP / 2 - 0.02], mat("frame", (0.22, 0.30, 0.42), 0.5, 0.3))
box("/World/Infeed/belt", [0, CONV_Y, CONV_TOP - 0.01], [1.6, 0.33, 0.01], mat("belt", (0.08, 0.08, 0.09), 0.9))
for k in range(-15, 16, 3):
    box(f"/World/Infeed/rail{k + 20}", [k * 0.1, CONV_Y + 0.35, CONV_TOP + 0.02], [0.03, 0.015, 0.03], mat("rail", (0.75, 0.6, 0.1), 0.4, 0.5))
# loop sorter: rectangular tray loop on the robot's other side, 12 chutes on the outer side
LOOP = dict(x0=-1.5, x1=1.5, y0=0.55, y1=1.55, z=0.62)
for i, (cx, cy, hx, hy) in enumerate([(0, LOOP["y0"], 1.6, 0.12), (0, LOOP["y1"], 1.6, 0.12), (LOOP["x0"], 1.05, 0.12, 0.62), (LOOP["x1"], 1.05, 0.12, 0.62)]):
    box(f"/World/Sorter/seg{i}", [cx, cy, LOOP["z"] / 2], [hx, hy, LOOP["z"] / 2], mat("sorter", (0.85, 0.86, 0.88), 0.5, 0.2))
    box(f"/World/Sorter/top{i}", [cx, cy, LOOP["z"] + 0.005], [hx - 0.01, hy - 0.01, 0.005], mat("tray", (0.15, 0.45, 0.75), 0.6))
for k in range(12):
    x = -1.35 + k * (2.7 / 11); y = LOOP["y1"] + 0.32
    box(f"/World/Chutes/c{k:02d}", [x, y, 0.35], [0.1, 0.18, 0.35], mat(f"chute{k % 2}", (0.9, 0.55, 0.15) if k % 2 else (0.95, 0.75, 0.2), 0.5))
box("/World/Tote", [TOTE[0], TOTE[1], 0.25], [0.2, 0.15, 0.25], mat("tote", (0.75, 0.12, 0.10), 0.6))
box("/World/Pedestal", [0, 0, 0.375], [0.18, 0.18, 0.375], mat("ped", (0.2, 0.22, 0.25), 0.5))
# camera gantry
box("/World/Gantry/post", [PICK_XY[0] - 0.5, CONV_Y - 0.45, (CONV_TOP + CAM_H) / 2], [0.03, 0.03, (CONV_TOP + CAM_H) / 2], mat("frame2", (0.3, 0.3, 0.32), 0.4, 0.6))
box("/World/Gantry/arm", [PICK_XY[0] - 0.25, CONV_Y - 0.45, CONV_TOP + CAM_H], [0.28, 0.03, 0.03], mat("frame2", (0.3, 0.3, 0.32)))
box("/World/Gantry/cam", [PICK_XY[0], PICK_XY[1], CONV_TOP + CAM_H + 0.09], [0.05, 0.04, 0.04], mat("cam", (0.05, 0.05, 0.06), 0.3))
# robot
MESH = CELLKIT.parent / "third_party/rbpodo_ros2/rbpodo_description/meshes/rb16_900e/collision"
links = {}
for ln in ["link0"] + ck.LINKS:
    x = UsdGeom.Xform.Define(stage, f"/World/RB16/{ln}")
    stl_mesh(f"/World/RB16/{ln}/mesh", MESH / f"{ln}.stl", mat("rb0", (0.2, 0.22, 0.25), 0.5) if ln == "link0" else mat("rb", (0.88, 0.89, 0.9), 0.4))
    links[ln] = x
set_T(links["link0"], ck.base_T())
tool = UsdGeom.Xform.Define(stage, "/World/Suction")
c1 = UsdGeom.Cylinder.Define(stage, "/World/Suction/body"); c1.CreateRadiusAttr(0.03); c1.CreateHeightAttr(SUCTION - 0.03)
UsdGeom.Xformable(c1).AddTranslateOp().Set(Gf.Vec3d(0, 0, -(SUCTION + 0.03) / 2)); bind(c1, mat("tool", (0.25, 0.25, 0.28), 0.4, 0.6))
c2 = UsdGeom.Cylinder.Define(stage, "/World/Suction/cup"); c2.CreateRadiusAttr(0.045); c2.CreateHeightAttr(0.03)
UsdGeom.Xformable(c2).AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.015)); bind(c2, mat("cup", (0.1, 0.1, 0.1), 0.9))
kin = ck.Kin()

def tcp_down(p, yaw=0.0):
    return ck.tool_tip_pose(np.asarray(p, float), [0, 0, -1], 0, ref=[math.cos(yaw), math.sin(yaw), 0])

def pose_robot(q):
    for ln in ck.LINKS: set_T(links[ln], kin.fk(q, ln))
    set_T(tool, kin.tip(q, "S"))

HOME = np.array([-1.5708, 0.0, 1.5708, 0.0, 1.5708, 0.0])

def ik(p, seed):
    s = kin.ik_tip(tcp_down(p), "S", [seed, HOME])
    return None if s is None else s[0]

# ---- parcel prim (one, re-textured per parcel)
parcel = UsdGeom.Xform.Define(stage, "/World/Parcel")
pbody = UsdGeom.Cube.Define(stage, "/World/Parcel/body"); pbody.CreateSizeAttr(1.0); bind(pbody, mat("card", (0.73, 0.56, 0.36), 0.8))
ptop = quad("/World/Parcel/top", [0, 0, 0.5005], 1.0, 1.0, mat("card", (0.73, 0.56, 0.36)))

def place_parcel(z, xy, yaw=0.0, tex=None):
    L, Wd, Hh = [d / 100 for d in z["dims"]]
    T = np.eye(4); cz, sz = math.cos(yaw), math.sin(yaw)
    T[:3, :3] = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.diag([L, Wd, Hh]); T[:3, 3] = [xy[0], xy[1], CONV_TOP + Hh / 2]
    set_T(parcel, T)
    if tex: UsdShade.MaterialBindingAPI.Apply(ptop.GetPrim()).Bind(mat(None, None, 0.7, tex=tex))
    return CONV_TOP + Hh

# ---- cameras
def camera(path, T, focal, hap, W, H):
    c = UsdGeom.Camera.Define(stage, path); c.CreateFocalLengthAttr(focal); c.CreateHorizontalApertureAttr(hap)
    c.CreateVerticalApertureAttr(hap * H / W); c.CreateClippingRangeAttr(Gf.Vec2f(0.01, 30)); set_T(c, T); return c
CW, CH = 3072, 2304   # ~0.31 mm/px at the belt (v2 2048 px = 0.47 mm/px)
Tcam = look((PICK_XY[0], PICK_XY[1], CONV_TOP + CAM_H), (PICK_XY[0], PICK_XY[1], CONV_TOP), up=(1, 0, 0))
camera("/World/PickCam", Tcam, 24.0, 20.955, CW, CH)
camera("/World/Overview", look((2.6, -2.4, 2.3), (0.0, 0.3, 0.6)), 18.0, 20.955, 1920, 1080)

def grab(cam_path, W, H, sub=32):
    rp = rep.create.render_product(cam_path, (W, H)); a = rep.AnnotatorRegistry.get_annotator("rgb"); a.attach([rp])
    rep.orchestrator.set_capture_on_play(False)
    for _ in range(2): rep.orchestrator.step(rt_subframes=sub, delta_time=0.0, pause_timeline=False)
    img = np.ascontiguousarray(a.get_data()[:, :, :3]); a.detach([rp]); rp.destroy(); return img

pose_robot(HOME)
for _ in range(10): app.update()

if args.cycle:
    out = {}
    hs = [0.10, 0.25, 0.35]
    for h in hs:
        top = CONV_TOP + h
        q_hover = ik([PICK_XY[0], PICK_XY[1], top + 0.15], HOME); q_pick = ik([PICK_XY[0], PICK_XY[1], top], q_hover)
        res = {}
        for dest, P in (("induct", INDUCT), ("tote", TOTE)):
            q_up = ik([P[0], P[1], P[2] + h + 0.20], q_pick); q_drop = ik([P[0], P[1], P[2] + h + 0.05], q_up)
            if any(q is None for q in (q_hover, q_pick, q_up, q_drop)):
                res[dest] = None; continue
            seq = [q_hover, q_pick, q_hover, q_up, q_drop, q_up, q_hover]
            mv = [ck.move_time(a, b) for a, b in zip(seq[:-1], seq[1:])]
            res[dest] = dict(move_s=round(sum(mv), 3), vacuum_s=2 * VAC_S, cycle_s=round(sum(mv) + 2 * VAC_S, 3), segments_s=[round(m, 3) for m in mv])
        out[f"parcel_h_{h}"] = res
    out["assumptions"] = dict(joint_vel_max=ck.CFG["robot"]["joint_vel_max"], joint_acc_max=ck.CFG["robot"]["joint_acc_max"], vacuum_each_s=VAC_S,
                              model="RB16-900E kinematic (Lula IK + trapezoid joint timing), no physics")
    (HERE / "results").mkdir(exist_ok=True); (HERE / "results" / "robot_cycle.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))

if args.capture:
    import random
    (HERE / "cam").mkdir(exist_ok=True)
    for s in args.sets:
        rows = [json.loads(l) for l in open(HERE / "img" / "sets" / f"{s}.jsonl", encoding="utf-8")]
        if args.limit: rows = rows[: args.limit]
        r = random.Random(7)
        only = set(open(args.ids).read().split()) if args.ids else None
        for z in rows:
            t0 = time.perf_counter()
            xy = PICK_XY + np.array([r.uniform(-0.04, 0.04), r.uniform(-0.04, 0.04)]); yaw = r.uniform(-0.35, 0.35)
            if only is not None and z["id"] not in only: continue
            place_parcel(z, xy, yaw=yaw, tex=HERE / "img" / "tex" / f"{z['id']}_top.png")
            for _ in range(12 if only is not None else 2): app.update()   # re-capture: more frames so the texture's full mip level is streamed in
            img = grab("/World/PickCam", CW, CH, 32 if only is not None else 16)
            imageio.imwrite(HERE / "cam" / f"{z['id']}.png", img); print(z["id"], round(time.perf_counter() - t0, 2), flush=True)

if args.stills:
    (HERE / "results" / "media").mkdir(parents=True, exist_ok=True)
    z = json.loads(open(HERE / "img" / "sets" / "stream.jsonl", encoding="utf-8").readline())
    top = place_parcel(z, PICK_XY, 0.2, HERE / "img" / "tex" / f"{z['id']}_top.png")
    q = ik([PICK_XY[0], PICK_XY[1], top + 0.08], HOME); pose_robot(q if q is not None else HOME)
    for _ in range(5): app.update()
    imageio.imwrite(HERE / "results" / "media" / "overview.png", grab("/World/Overview", 1920, 1080, 64))
    imageio.imwrite(HERE / "results" / "media" / "pickcam_example.png", grab("/World/PickCam", CW, CH, 32))
if args.video:
    # LinkedIn clip: front view, one clip per parcel = arrival on the infeed + pick-and-place to induct (OK) or tote (exception).
    # Kinematic only; segment durations from ck.move_time (same model as --cycle). Frames -> results/video/<tag>/NNNN.png
    FPS = 24
    for g in ("post", "arm", "cam"): UsdGeom.Imageable(stage.GetPrimAtPath(f"/World/Gantry/{g}")).MakeInvisible()   # post blocked the front view
    camera("/World/Front", look((0.7, -2.9, 2.25), (0.05, 0.2, 0.6)), 20.0, 20.955, 1920, 1080)
    rp = rep.create.render_product("/World/Front", (1920, 1080)); ann = rep.AnnotatorRegistry.get_annotator("rgb"); ann.attach([rp])
    rep.orchestrator.set_capture_on_play(False)
    def shot(path):
        rep.orchestrator.step(rt_subframes=args.sub, delta_time=0.0, pause_timeline=False)
        imageio.imwrite(path, np.ascontiguousarray(ann.get_data()[:, :, :3]))
    def ease(t): return t * t * (3 - 2 * t)
    def parcel_T(z, xy, yaw, zc=None):
        L, Wd, Hh = [d / 100 for d in z["dims"]]; T = np.eye(4); cz, sz = math.cos(yaw), math.sin(yaw)
        T[:3, :3] = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.diag([L, Wd, Hh]); T[:3, 3] = [xy[0], xy[1], CONV_TOP + Hh / 2 if zc is None else zc]
        return T
    meta = {}
    for spec in args.video:
        sid, dest = spec.split(":")                      # e.g. fc_hard_0079:tote
        s = sid.rsplit("_", 1)[0]
        z = next(json.loads(l) for l in open(HERE / "img" / "sets" / f"{s}.jsonl", encoding="utf-8") if json.loads(l)["id"] == sid)
        out = HERE / "results" / "video" / f"{sid}_{dest}"; out.mkdir(parents=True, exist_ok=True); n = 0
        h = z["dims"][2] / 100; top = CONV_TOP + h; yaw = 0.15
        UsdShade.MaterialBindingAPI.Apply(ptop.GetPrim()).Bind(mat(None, None, 0.7, tex=HERE / "img" / "tex" / f"{sid}_top.png"))
        q_hover = ik([PICK_XY[0], PICK_XY[1], top + 0.15], HOME); q_pick = ik([PICK_XY[0], PICK_XY[1], top], q_hover)
        P = INDUCT if dest == "induct" else TOTE
        q_up = ik([P[0], P[1], P[2] + h + 0.20], q_pick); q_drop = ik([P[0], P[1], P[2] + h + 0.05], q_up)
        pose_robot(q_hover)
        # 1) arrival: 2.0 s slide from x=-1.25 to the pick point
        for k in range(int(2.0 * FPS)):
            x = -1.25 + (PICK_XY[0] + 1.25) * ease(k / (2.0 * FPS - 1))
            set_T(parcel, parcel_T(z, [x, PICK_XY[1]], yaw)); app.update(); shot(out / f"{n:04d}.png"); n += 1
        n_arrive = n
        # 2) pick and place
        seq = [q_hover, q_pick, q_hover, q_up, q_drop, q_up, q_hover]; segs = []
        T_par = parcel_T(z, PICK_XY, yaw); rel = None
        for j, (a, b) in enumerate(zip(seq[:-1], seq[1:])):
            d = ck.move_time(a, b); m = max(2, int(round(d * FPS))); segs.append(round(d, 3))
            for k in range(m):
                q = a + (b - a) * ease((k + 1) / m); pose_robot(q)
                if rel is not None: set_T(parcel, kin.tip(q, "S") @ rel)
                app.update(); shot(out / f"{n:04d}.png"); n += 1
            if j == 0:                                   # suction on at the pick pose
                rel = np.linalg.inv(kin.tip(b, "S")) @ T_par
                for _ in range(int(VAC_S * FPS)): shot(out / f"{n:04d}.png"); n += 1
            if j == 3:                                   # suction off at the drop pose
                Tp = kin.tip(b, "S") @ rel; rel = None
                if dest == "tote": Tp[2, 3] = 0.5 - h / 2 + h / 2 * 0  # sink into the tote
                set_T(parcel, Tp)
                for _ in range(int(VAC_S * FPS)): app.update(); shot(out / f"{n:04d}.png"); n += 1
        meta[f"{sid}_{dest}"] = dict(dest=dest, frames=n, arrive_frames=n_arrive, segments_s=segs, cycle_s=round(sum(segs) + 2 * VAC_S, 3), fps=FPS)
        print(sid, meta[f"{sid}_{dest}"], flush=True)
    mp = HERE / "results" / "video" / "meta2.json"; old = json.loads(mp.read_text()) if mp.exists() else {}
    old.update(meta); mp.write_text(json.dumps(old, indent=1))
app.close()
