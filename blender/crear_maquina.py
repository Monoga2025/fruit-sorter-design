"""Clasificadora de limón Tahití — tambor cónico de varillas (ED-01, Grupo 09).

Construye la máquina en Blender con las MISMAS cotas del documento y la anima.
Uso (desde esta carpeta):
    blender -b -P crear_maquina.py                 -> crea maquina_clasificadora.blend
    blender -b -P crear_maquina.py -- --stills     -> además renderiza 3 imágenes
    blender -b -P crear_maquina.py -- --anim       -> además renderiza el video mp4
Unidades: el modelo se dibuja en mm del documento y se pasa a metros (1 mm = 0,001 m).

IMPORTANTE (honestidad): el movimiento del tambor, los engranajes y la caída por zonas siguen la
geometría del diseño. La VELOCIDAD DE AVANCE del fruto (50 mm/s) es un SUPUESTO ilustrativo: en el
diseño real se mide en el Motion Study de SolidWorks. La caída está en cámara lenta (x3).
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

# ============================================================== parámetros (mm) = design.py
N_ROD, D_ROD, G0, G1, L = 16, 12.0, 38.0, 72.0, 600.0
DELTA, H = 5.0, 700.0
THRESH = [42.0, 48.0, 58.0]
XDIV = [160.0, 265.0, 440.0]
X_BRG, X_GEAR, X_SHAFT = (700.0, 900.0), 800.0, (560.0, 980.0)
Y_MOTOR, MOTOR_X, MOTOR_R = 156.0, (815.0, 1095.0), 55.0
M, Z1, Z2, B_FACE = 4.0, 26, 52, 30.0
TRAY_X, TRAY_Y, TRAY_RIM, TRAY_DEPTH = (-40.0, 640.0), (-270.0, 150.0), 449.0, 120.0
FRAME_X, FRAME_HALF_Y, RAIL_Z = (-250.0, 1100.0), 290.0, 480.0
HOPPER_PATH, HOPPER_W = [(-420.0, 800.0), (-160.0, 640.0), (40.0, 610.0)], 100.0
BRG_HALF_Y, BRG_BASE, BRG_TOP = 82.5, H - 42.9, H + 45.0

N_DRUM_RPM = 28.3
W = 2 * math.pi * N_DRUM_RPM / 60                  # rad/s
FPS, FRAMES = 24, 600                              # 25 s
V_AXIAL = 50.0                                     # mm/s  (SUPUESTO ilustrativo)
SLOW = 3.0                                         # factor de cámara lenta en la caída
MM = 0.001


def rin_gap(g):
    return (g + D_ROD) / (2 * math.sin(math.pi / N_ROD))


R0, R1 = rin_gap(G0), rin_gap(G1)


def r_of_x(x):
    return R0 + (R1 - R0) * x / L


def P(x, y, z):
    return Vector((x * MM, y * MM, z * MM))


# ============================================================== utilidades
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def mat(name, color, metal=0.0, rough=0.5, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    return m


STEEL = mat("Inox", (0.72, 0.74, 0.76), 0.9, 0.28)
STEEL_D = mat("Acero eje", (0.45, 0.48, 0.52), 0.9, 0.3)
FRAME_M = mat("Bastidor", (0.30, 0.32, 0.36), 0.6, 0.45)
GEAR_M = mat("Engranaje", (0.20, 0.42, 0.78), 0.7, 0.35)
MOTOR_M = mat("Motor", (0.95, 0.55, 0.25), 0.3, 0.45)
BRG_M = mat("Chumacera", (0.62, 0.62, 0.64), 0.7, 0.4)
GLASS = mat("Carcasa", (0.7, 0.75, 0.8), 0.0, 0.2, 0.22)
DISC = mat("Tapa", (0.55, 0.7, 0.9), 0.2, 0.3, 0.30)
HOP_M = mat("Tolva", (0.62, 0.78, 0.92), 0.5, 0.35)
CHAIN_M = mat("Cadena", (0.7, 0.45, 0.1), 0.6, 0.4)
LEMON = mat("Limon", (0.95, 0.85, 0.15), 0.0, 0.55)
FLOOR = mat("Piso", (0.30, 0.32, 0.36), 0.0, 0.9)
ZMAT = [mat(f"Zona{i}", c, 0.0, 0.55) for i, c in enumerate(
    [(0.93, 0.45, 0.42), (0.98, 0.72, 0.30), (0.45, 0.80, 0.50), (0.35, 0.62, 0.90)])]
TXT = mat("Texto", (1.0, 1.0, 1.0), 0.0, 0.8)


def adopt(o, parent):
    if parent is not None:
        bpy.context.view_layer.update()
        o.parent = parent
        o.matrix_parent_inverse = parent.matrix_world.inverted()
    return o


def box(name, x0, x1, y0, y1, z0, z1, material, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = name
    o.location = P((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    o.scale = Vector(((x1 - x0) * MM, (y1 - y0) * MM, (z1 - z0) * MM))
    o.data.materials.append(material)
    return adopt(o, parent)


def cyl(name, p0, p1, r, material, parent=None, verts=32):
    a, b = Vector(p0) * MM, Vector(p1) * MM
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r * MM, depth=d.length)
    o = bpy.context.active_object
    o.name = name
    o.location = (a + b) / 2
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = d.to_track_quat("Z", "Y")
    o.data.materials.append(material)
    return adopt(o, parent)


def empty(name, loc_mm):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = "ARROWS"
    e.empty_display_size = 0.08
    e.location = P(*loc_mm)
    bpy.context.collection.objects.link(e)
    e.rotation_mode = "XYZ"
    bpy.context.view_layer.update()
    return e


def smooth(o):
    for p in o.data.polygons:
        p.use_smooth = True


# ============================================================== ejes de giro (empties animados)
drum = empty("GIRO_tambor", (0, 0, H))
pin = empty("GIRO_pinon_motor", (0, Y_MOTOR, H))

# ============================================================== tambor: varillas, anillos, tapa, eje
for k in range(N_ROD):
    phi = math.radians(11.25 + 22.5 * k)            # desde abajo hacia -y
    p0 = (0, -R0 * math.sin(phi), H - R0 * math.cos(phi))
    p1 = (L, -R1 * math.sin(phi), H - R1 * math.cos(phi))
    o = cyl(f"Varilla_{k+1:02d}", p0, p1, D_ROD / 2, STEEL, drum, 16)
    smooth(o)
bpy.ops.mesh.primitive_torus_add(major_radius=R0 * MM, minor_radius=5 * MM, major_segments=96, minor_segments=14)
ring = bpy.context.active_object
ring.name = "Anillo_pequeno_P2"
ring.rotation_euler = (0, math.pi / 2, 0)
ring.location = P(0, 0, H)
ring.data.materials.append(STEEL)
smooth(ring)
adopt(ring, drum)
cyl("Tapa_extremo_grande_P3", (L - 1.5, 0, H), (L + 1.5, 0, H), R1, DISC, drum, 96)
cyl("Cubo_P3", (L - 40, 0, H), (L + 10, 0, H), 32, STEEL_D, drum, 32)
cyl("Eje_P1", (X_SHAFT[0], 0, H), (X_SHAFT[1], 0, H), 15, STEEL_D, drum, 32)

# ============================================================== engranajes (dientes reales, 2:1)
def make_gear(name, z, x0, width, yc, zc, sgn, phase, material, parent):
    rp = M * z / 2
    rf, ra, pitch = rp - 1.25 * M, rp + M, 2 * math.pi / z
    pts = []
    for i in range(z):
        ac = (i + phase) * pitch
        for dr, da in ((rf, -0.34), (ra, -0.18), (ra, 0.18), (rf, 0.34)):
            a = ac + da * pitch
            pts.append((dr * math.cos(a), dr * math.sin(a)))
    n = len(pts)
    verts = []
    for x in (x0, x0 + width):
        for u, v in pts:
            verts.append(P(x, yc + sgn * u, zc + sgn * v))
    faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j, n + i])
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    return adopt(o, parent)


make_gear("Rueda_P6_z52", Z2, X_GEAR - 15, B_FACE, 0, H, +1, 0.0, GEAR_M, drum)
make_gear("Pinon_P5_z26", Z1, X_GEAR - 15, B_FACE, Y_MOTOR, H, -1, 0.5, GEAR_M, pin)
cyl("Eje_motor", (X_GEAR - 15, Y_MOTOR, H), (MOTOR_X[0], Y_MOTOR, H), 10, STEEL_D, pin)

# ============================================================== motorreductor, base, carcasa
cyl("Motorreductor_C1", (MOTOR_X[0], Y_MOTOR, H), (MOTOR_X[1], Y_MOTOR, H), MOTOR_R, MOTOR_M, None, 48)
cyl("Motor_aletas", (MOTOR_X[0] + 150, Y_MOTOR, H), (MOTOR_X[1], Y_MOTOR, H), MOTOR_R + 8, MOTOR_M, None, 48)
box("Base_motor_P13", MOTOR_X[0] + 10, MOTOR_X[1] - 10, Y_MOTOR - 70, Y_MOTOR + 70, H - MOTOR_R - 8, H - MOTOR_R - 4, STEEL)
for xx in (MOTOR_X[0] + 25, MOTOR_X[1] - 35):
    for sy in (-1, 1):
        box("Pata_base_motor", xx, xx + 6, Y_MOTOR + sy * 62 - 3, Y_MOTOR + sy * 62 + 3, RAIL_Z, H - MOTOR_R - 4, STEEL)
box("Carcasa_P12", X_GEAR - 45, X_GEAR + 45, -125, Y_MOTOR + 70, H - 140, H + 140, GLASS)

# ============================================================== chumaceras y soportes
for xb in X_BRG:
    box("Chumacera_C2", xb - 24, xb + 24, -BRG_HALF_Y, BRG_HALF_Y, BRG_BASE, BRG_TOP, BRG_M)
    box("Soporte_P8", xb - 30, xb + 30, -80, 80, RAIL_Z, BRG_BASE, STEEL)

# ============================================================== bastidor soldado (40x40)
legs_x = (FRAME_X[0], 440.0, FRAME_X[1])
for xl in legs_x:
    for yl in (-FRAME_HALF_Y, FRAME_HALF_Y):
        box("Pata", xl - 20, xl + 20, yl - 20, yl + 20, 0, RAIL_Z, FRAME_M)
        box("Pie_niveladora", xl - 30, xl + 30, yl - 30, yl + 30, -14, 0, STEEL_D)
for yl in (-FRAME_HALF_Y, FRAME_HALF_Y):
    box("Riel_sup", FRAME_X[0] - 20, FRAME_X[1] + 20, yl - 20, yl + 20, RAIL_Z - 40, RAIL_Z, FRAME_M)
    box("Riel_medio", FRAME_X[0] - 20, FRAME_X[1] + 20, yl - 20, yl + 20, 289, 329, FRAME_M)
    box("Riel_inf", FRAME_X[0] - 20, FRAME_X[1] + 20, yl - 20, yl + 20, 100, 140, FRAME_M)
for xl in list(legs_x) + [X_BRG[0], X_BRG[1]]:
    box("Travesano_sup", xl - 20, xl + 20, -FRAME_HALF_Y, FRAME_HALF_Y, RAIL_Z - 40, RAIL_Z, FRAME_M)
for xl in legs_x:
    box("Travesano_inf", xl - 20, xl + 20, -FRAME_HALF_Y, FRAME_HALF_Y, 100, 140, FRAME_M)
for xl in (100.0, 500.0):
    box("Travesano_colector", xl - 20, xl + 20, -FRAME_HALF_Y, FRAME_HALF_Y, 289, 329, FRAME_M)
box("Poste_tolva_1", FRAME_X[0] - 20, FRAME_X[0] + 20, -20, 20, RAIL_Z, 690, FRAME_M)
box("Poste_tolva_2", -440, -400, -20, 20, 0, 790, FRAME_M)
box("Travesano_poste", -440, -400 + 0.1, -20, 20, 0, 0.1, FRAME_M)

# ============================================================== tolva: canal en U de chapa
def plate(name, a, b, width, thick, normal_shift, y_shift, material):
    (x0, z0), (x1, z1) = a, b
    dx, dz = x1 - x0, z1 - z0
    length = math.hypot(dx, dz) + 6
    theta = math.atan2(-dz, dx)
    nrm = Vector((math.sin(theta), 0, math.cos(theta)))
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.active_object
    o.name = name
    o.scale = Vector((length * MM, width * MM, thick * MM))
    o.rotation_euler = (0, theta, 0)
    mid = Vector(((x0 + x1) / 2, y_shift, (z0 + z1) / 2)) + nrm * normal_shift
    o.location = mid * MM
    o.data.materials.append(material)
    return o


for i in range(len(HOPPER_PATH) - 1):
    a, b = HOPPER_PATH[i], HOPPER_PATH[i + 1]
    plate(f"Tolva_fondo_{i}", a, b, HOPPER_W, 3, -1.5, 0, HOP_M)
    for sy in (-1, 1):
        plate(f"Tolva_pared_{i}", a, b, 3, 60, 28.5, sy * (HOPPER_W / 2 + 1.5), HOP_M)

# ============================================================== colector (una pieza) + divisores
ZB = [TRAY_X[0]] + XDIV + [TRAY_X[1]]
floor_z = TRAY_RIM - TRAY_DEPTH
for i in range(4):
    box(f"Colector_fondo_Z{i}", ZB[i], ZB[i + 1], TRAY_Y[0], TRAY_Y[1], floor_z - 3, floor_z, ZMAT[i])
for sy, yy in ((-1, TRAY_Y[0]), (1, TRAY_Y[1])):
    box("Colector_pared_lateral", TRAY_X[0], TRAY_X[1], yy - (3 if sy < 0 else 0), yy + (0 if sy < 0 else 3), floor_z, floor_z + (30 if sy < 0 else TRAY_DEPTH), STEEL)
for xx in TRAY_X:
    box("Colector_pared_extremo", xx - (3 if xx == TRAY_X[0] else 0), xx + (0 if xx == TRAY_X[0] else 3), TRAY_Y[0], TRAY_Y[1], floor_z, TRAY_RIM, STEEL)
for x in XDIV:
    box("Divisor_P11", x - 1.5, x + 1.5, TRAY_Y[0], TRAY_Y[1], floor_z, TRAY_RIM + 30, STEEL)

# ============================================================== piso
bpy.ops.mesh.primitive_plane_add(size=6)
fl = bpy.context.active_object
fl.name = "Piso"
fl.location = P(450, 0, -14.5)
fl.data.materials.append(FLOOR)

# ============================================================== animación del giro
def key_rot(obj, sign):
    obj.rotation_euler = (0, 0, 0)
    obj.keyframe_insert("rotation_euler", frame=1)
    obj.rotation_euler = (sign * W * (FRAMES - 1) / FPS, 0, 0)
    obj.keyframe_insert("rotation_euler", frame=FRAMES)
    for fc in obj.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


key_rot(drum, -1.0)        # antihorario visto desde el extremo de alimentación
key_rot(pin, +2.0)         # relación 2:1, sentido opuesto

# ============================================================== limones (trayectoria ilustrativa)
FRUITS = [(40, 1.0), (46, 3.0), (52, 5.0), (56, 7.0), (62, 9.0), (66, 11.0)]
PHI = math.radians(22.5)
G_EARTH = 9.81


def rest_pos(x, d):
    r_in = r_of_x(x) - D_ROD / 2
    rho = r_in - d / 2 + 1.0
    return Vector((x, -rho * math.sin(PHI), H - rho * math.cos(PHI))), rho


def hopper_point(s):
    """posición sobre la tolva a distancia s (mm) del inicio, y normal."""
    pts = HOPPER_PATH
    acc = 0.0
    for i in range(len(pts) - 1):
        (x0, z0), (x1, z1) = pts[i], pts[i + 1]
        seg = math.hypot(x1 - x0, z1 - z0)
        if s <= acc + seg or i == len(pts) - 2:
            t = min(1.0, (s - acc) / seg)
            th = math.atan2(-(z1 - z0), x1 - x0)
            return Vector((x0 + (x1 - x0) * t, 0, z0 + (z1 - z0) * t)), Vector((math.sin(th), 0, math.cos(th)))
        acc += seg


HOP_LEN = sum(math.hypot(HOPPER_PATH[i + 1][0] - HOPPER_PATH[i][0], HOPPER_PATH[i + 1][1] - HOPPER_PATH[i][1]) for i in range(2))
A_HOP = 700.0                 # mm/s² de rodadura en la tolva (ilustrativo)
T_HOP = math.sqrt(2 * HOP_LEN / A_HOP)
T_DROP = 0.35


def fruit_track(d, t0):
    """lista de (frame, posición mm) para un limón de diámetro d."""
    x_fall = L * (d + DELTA - G0) / (G1 - G0)
    out = []
    # instante de salida: la ranura (hueco entre varillas) debe estar bajo el fruto
    pos0, rho = rest_pos(x_fall, d)
    t_axial0 = t0 + T_HOP + T_DROP
    t_nom = t_axial0 + (x_fall - 40.0) / V_AXIAL
    r_out = r_of_x(x_fall)
    psi = math.degrees(math.asin(min(1.0, rho * math.sin(PHI) / r_out)))
    deg_w = math.degrees(W)
    t_fall = t_nom
    for _ in range(4000):
        if (psi - deg_w * t_fall) % 22.5 < 1.5:
            break
        t_fall += 0.002
    # estado en el instante de la caída
    pos = pos0.copy()
    vy = -W * rho * math.cos(PHI) / SLOW / 1000.0
    vz = W * rho * math.sin(PHI) / SLOW / 1000.0
    vx = V_AXIAL / 1000.0
    y_, z_, x_ = pos.y / 1000.0, pos.z / 1000.0, pos.x / 1000.0
    land_z = (floor_z + d / 2) / 1000.0
    g_eff = G_EARTH / SLOW ** 2
    resting = False
    for f in range(1, FRAMES + 1):
        t = (f - 1) / FPS
        if t < t0:
            p = None
        elif t < t0 + T_HOP:
            s = 0.5 * A_HOP * (t - t0) ** 2
            q, nrm = hopper_point(min(s, HOP_LEN))
            p = q + nrm * (d / 2)
        elif t < t_axial0:
            q, nrm = hopper_point(HOP_LEN)
            a = q + nrm * (d / 2)
            b, _r = rest_pos(40.0, d)
            u = (t - t0 - T_HOP) / T_DROP
            u = u * u * (3 - 2 * u)
            p = a.lerp(b, u)
        elif t < t_fall:
            x = 40.0 + V_AXIAL * (t - t_axial0)
            p, _r = rest_pos(min(x, x_fall), d)
        else:
            if not resting:
                steps = 6
                dt = (1.0 / FPS) / steps
                for _s in range(steps):
                    vz -= g_eff * dt
                    x_ += vx * dt
                    y_ += vy * dt
                    z_ += vz * dt
                    if z_ <= land_z:
                        z_ = land_z
                        if abs(vz) < 0.02:
                            resting = True
                            vz = vy = vx = 0.0
                        else:
                            vz = -0.35 * vz
                            vy *= 0.5
                            vx *= 0.5
            p = Vector((x_ * 1000.0, y_ * 1000.0, z_ * 1000.0))
        out.append((f, p))
    return out


for idx, (d, t0) in enumerate(FRUITS):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, segments=32, ring_count=16)
    fr = bpy.context.active_object
    fr.name = f"Limon_{idx+1}_d{d}mm"
    fr.scale = Vector((1.2 * d / 2 * MM, d / 2 * MM, d / 2 * MM))
    fr.data.materials.append(LEMON)
    smooth(fr)
    for f, p in fruit_track(d, t0):
        vis = p is not None
        fr.hide_render = not vis
        fr.hide_viewport = not vis
        fr.keyframe_insert("hide_render", frame=f)
        fr.keyframe_insert("hide_viewport", frame=f)
        if vis:
            fr.location = p * MM
            fr.keyframe_insert("location", frame=f)
    for fc in fr.animation_data.action.fcurves:
        if fc.data_path == "location":
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

# ============================================================== cámara, luces, etiquetas
cam_data = bpy.data.cameras.new("Camara")
cam_data.lens = 32
cam = bpy.data.objects.new("Camara", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = P(1150, -2150, 1120)
target = empty("Objetivo_camara", (380, 0, 520))
tc = cam.constraints.new("TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
scene.camera = cam

sun_data = bpy.data.lights.new("Sol", "SUN")
sun_data.energy = 2.2
sun = bpy.data.objects.new("Sol", sun_data)
sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
bpy.context.collection.objects.link(sun)
area_data = bpy.data.lights.new("Relleno", "AREA")
area_data.energy = 120
area_data.size = 3
area = bpy.data.objects.new("Relleno", area_data)
area.location = P(300, -1500, 1800)
area.rotation_euler = (math.radians(35), 0, 0)
bpy.context.collection.objects.link(area)

world = bpy.data.worlds.new("Mundo")
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.42, 0.50, 0.62, 1)
bg.inputs["Strength"].default_value = 0.55
scene.world = world


def label(text, loc_mm, size=0.055):
    bpy.ops.object.text_add()
    o = bpy.context.active_object
    o.data.body = text
    o.data.size = size
    o.data.align_x = "CENTER"
    o.data.extrude = 0.002
    o.location = P(*loc_mm)
    o.data.materials.append(TXT)
    c = o.constraints.new("TRACK_TO")
    c.target = cam
    c.track_axis = "TRACK_Z"
    c.up_axis = "UP_Y"
    return o


label("TOLVA\n(entrada del fruto)", (-330, 0, 900))
label("TAMBOR CONICO — 16 varillas\nluz 38 a 72 mm · 28 rpm", (300, 0, 1030), 0.055)
label("PIÑON z=26 → RUEDA z=52\nrelacion 2:1, giro opuesto", (850, 300, 960), 0.04)
label("MOTORREDUCTOR", (1130, 156, 800), 0.045)
label("CHUMACERAS", (800, -150, 810), 0.04)
for i in range(4):
    label(f"Z{i}\n{['<42', '42–48', '48–58', '≥58'][i]}", ((ZB[i] + ZB[i + 1]) / 2, -330, floor_z - 70), 0.04)

# ============================================================== render
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, FRAMES
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
try:
    scene.render.engine = "BLENDER_EEVEE_NEXT"
except Exception:
    scene.render.engine = "BLENDER_EEVEE"
try:
    scene.view_settings.view_transform = "Standard"
except Exception:
    pass

blend_path = os.path.join(HERE, "maquina_clasificadora.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print("GUARDADO", blend_path)

if "--stills" in ARGS:
    for fr_no in (1, 200, 330, 560):
        scene.frame_set(fr_no)
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = os.path.join(HERE, f"vista_cuadro_{fr_no:03d}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDER", scene.render.filepath)

if "--anim" in ARGS:
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = os.path.join(HERE, "maquina_funcionando.mp4")
    bpy.ops.render.render(animation=True)
    print("VIDEO", scene.render.filepath)
