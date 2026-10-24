# -*- coding: utf-8 -*-
# Maze puzzle (jezgra + rukavac) - CadQuery skripta, seed 13305
# Pokretanje: pip install cadquery, zatim: python maze_cadquery.py
# Izlaz: maze_core.step i maze_sleeve.step (mm). Rezanje utora moze potrajati (nekoliko minuta).
# Utori: kruzni presjek; obodni = pravi torus-lukovi (revolve), aksijalni = valjci, zavoji = kugle.
import math
import cadquery as cq

PRINT_ORIENT = True   # True = orijentacija kao u STL-u (otvorena strana gore)

H = 60          # visina jezgre
R = 20          # polumjer jezgre
DP = 2.244         # dubina utora
HW = 2.244         # pola sirine utora
PR = 1.944         # polumjer pina
EXT = 0        # produzetak pina
CL = 0.4         # zracnost jezgra-rukavac
WL = 2.5         # stijenka rukavca
RC = 9         # polumjer supljine (0 = puna)
CT = 3         # dno / poklopac
ZF = 57         # visina dna supljine
W = 28              # broj segmenata po opsegu
HH = 13             # broj segmenata po visini
GOAL_ROW = 5      # red cilja (pin)
V = H / HH
CARVE = ["1000000000000000000000000000","1111111011111011111111111110","0000001010100010100000000010","1011101010111110111111111011","0010101010000000000000001000","1110111010111110111011101110","1000000010100010101010100010","1011101110101110101010111011","0010001000101000101010001000","1011111010101111101011101111","1010000010100000001000100000","1110111111111111101111111110","0000000000000000000000000000"]

RS = R + CL
RO = RS + WL
LD = H + CL
LT = LD + CT
HWC = (HW ** 2 + DP ** 2) / (2.0 * DP)   # polumjer kruznog presjeka utora
RCC = R + HWC - DP                         # radijus sredista presjeka


def pt(r, a, z):
    return cq.Vector(r * math.cos(a), r * math.sin(a), z)


def ang(x):
    return 2.0 * math.pi * (x + 0.5) / W


def cen(x, y):
    return pt(RCC, ang(x), (y + 0.5) * V)


def capsule(a, b):
    d = b - a
    return cq.Solid.makeCylinder(HWC, d.Length, a, d.normalized())


# ---- jezgra ----
def adiff(p, q):
    return (p - q + math.pi) % (2 * math.pi) - math.pi


def arc_cutter(z, a0, a1):
    # pravi torus-sektor (revolve kruga oko osi Z) od kuta a0 do a1
    dr = a1 - a0
    d = math.degrees(dr)
    s = cq.Workplane('XZ').pushPoints([(RCC, z)]).circle(HWC).revolve(d, (0, 0, 0), (0, 1, 0))
    c = s.val().Center()
    phi = math.atan2(c.y, c.x)
    if abs(adiff(phi, -dr / 2.0)) < abs(adiff(phi, dr / 2.0)):
        s = s.rotate((0, 0, 0), (0, 0, 1), d)   # revolve je isao u suprotnom smjeru
    return s.rotate((0, 0, 0), (0, 0, 1), math.degrees(a0)).val()


def arcs(z, a0, a1):
    n = max(1, int(math.ceil((a1 - a0) / (2.0 * math.pi / 3.0))))
    return [arc_cutter(z, a0 + (a1 - a0) * i / n, a0 + (a1 - a0) * (i + 1) / n) for i in range(n)]


def runs(flags):
    n = len(flags)
    res = []
    if all(flags):
        return res
    for s0 in range(n):
        if flags[s0] and not flags[(s0 - 1) % n]:
            k = 1
            while flags[(s0 + k) % n]:
                k += 1
            res.append((s0, k))
    return res


def carved(x, y):
    return 0 <= y < HH and CARVE[y][x % W] == '1'


tools = []
# obodni utori: jedan torus-luk po cijeloj ravnoj dionici
for y in range(HH):
    row = [carved(x, y) for x in range(W)]
    for s0, k in runs(row):
        if k >= 2:
            tools += arcs((y + 0.5) * V, ang(s0), ang(s0 + k - 1))
# aksijalni utori: jedan valjak po cijeloj dionici
for x in range(W):
    y = 0
    while y < HH:
        if carved(x, y):
            y0 = y
            while y < HH and carved(x, y):
                y += 1
            y1 = y - 1
            if y1 > y0:
                z0 = (y0 + 0.5) * V
                if y0 == 0 and x == 0:
                    z0 = -2.0 * HW      # ulaz otvoren na rubu z = 0
                z1 = (y1 + 0.5) * V
                tools.append(cq.Solid.makeCylinder(HWC, z1 - z0, pt(RCC, ang(x), z0), cq.Vector(0, 0, 1)))
        else:
            y += 1
# kugle samo gdje treba (zavoji i krajevi staza)
for y in range(HH):
    for x in range(W):
        if not carved(x, y):
            continue
        if (carved(x - 1, y) and carved(x + 1, y)) or (carved(x, y - 1) and carved(x, y + 1)):
            continue
        a = cen(x, y)
        tools.append(cq.Workplane('XY').sphere(HWC).translate((a.x, a.y, a.z)).val())

base = cq.Workplane('XY').circle(R).extrude(H)
if RC > 0:
    base = base.cut(cq.Workplane('XY').circle(RC).extrude(ZF))
shape = base.val()
print('Rezem %d alata za utore ...' % len(tools))
# rez jedan po jedan: cut(*tools) u jednom koraku daje nevaljanu geometriju
# (degenerirana ploha, vrh s tolerancijom ~2.7 mm, rupe u STL-u)
for t in tools:
    shape = shape.cut(t)
if not shape.isValid():
    raise SystemExit('GRESKA: jezgra nije valjano tijelo (isValid=False)')
core = cq.Workplane('XY').newObject([shape])

# ---- rukavac s pinom ----
sleeve = cq.Workplane('XY').circle(RO).extrude(LT).cut(
    cq.Workplane('XY').circle(RS).extrude(LD))
ZP = LD - (2 * GOAL_ROW + 1.5) * V
PCB = RS + 0.3
PCX = PCB - EXT
half = cq.Workplane('XY').box(2 * PR, 2 * PR, 2 * PR, centered=(False, True, True)).translate((-2 * PR, 0, 0))
dome = cq.Workplane('XY').sphere(PR).intersect(half).translate((PCX, 0, ZP))
sleeve = sleeve.union(dome)
if EXT > 0.05:
    shaft = cq.Solid.makeCylinder(PR, EXT, cq.Vector(PCX, 0, ZP), cq.Vector(1, 0, 0))
    sleeve = sleeve.union(cq.Workplane('XY').newObject([shaft]))

if PRINT_ORIENT:
    core = core.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, H))
    sleeve = sleeve.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, LT))

cq.exporters.export(core, 'maze_core.step')
cq.exporters.export(sleeve, 'maze_sleeve.step')
# STL: tolerance = odstupanje od prave plohe (mm), angularTolerance u radijanima
cq.exporters.export(core, 'maze_core.stl', tolerance=0.01, angularTolerance=0.1)
cq.exporters.export(sleeve, 'maze_sleeve.stl', tolerance=0.01, angularTolerance=0.1)

# parametri za preview / cults_upload.py
import json
with open('maze_params.json', 'w', encoding='utf-8') as f:
    json.dump({'seed': 13305, 'H': H, 'R': R, 'DP': DP, 'HW': HW, 'PR': PR, 'CL': CL,
               'WL': WL, 'RC': RC, 'CT': CT, 'ZF': ZF, 'W': W, 'HH': HH, 'GOAL_ROW': GOAL_ROW,
               'RS': RS, 'RO': RO, 'LD': LD, 'LT': LT, 'ZP': ZP, 'PRINT_ORIENT': PRINT_ORIENT,
               'CARVE': CARVE}, f, indent=2)
print('Gotovo: maze_core.step/.stl, maze_sleeve.step/.stl, maze_params.json')
