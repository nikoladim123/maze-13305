# -*- coding: utf-8 -*-
# Maze puzzle (jezgra + rukavac): generator labirinta + CadQuery model.
# Port HTML generatora (isti RNG i algoritam -> isti labirint za isti seed).
# Utori: kruzni presjek; obodni = torus-lukovi (revolve), aksijalni = valjci, zavoji = kugle.
import json
import math
import os

# zadane vrijednosti kao u HTML generatoru (tl = tolerancija pin-maze)
DEFAULTS = dict(H=60, D=40, pw=4.5, dp=2, cl=0.4, tl=0.3, pl=0, wl=2.5, cv=18, ct=3, seed=1)


# ---------------- labirint ----------------
def mulberry32(a):
    a &= 0xFFFFFFFF

    def imul(x, y):
        return (x * y) & 0xFFFFFFFF

    def rnd():
        nonlocal a
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0
    return rnd


def gen_maze(cols, rows, rnd):
    # DFS labirint na cilindru (stupci se zatvaraju u krug), ulaz (0,0), cilj = najdalja celija u zadnjem redu
    mk = lambda: [[0] * cols for _ in range(rows)]
    vis, oR, oU = mk(), mk(), mk()
    st = [(0, 0)]
    vis[0][0] = 1
    while st:
        c, r = st[-1]
        cr, cl = (c + 1) % cols, (c + cols - 1) % cols
        nb = []
        if not vis[r][cr]:
            nb.append((cr, r, ('R', r, c)))
        if not vis[r][cl]:
            nb.append((cl, r, ('R', r, cl)))
        if r < rows - 1 and not vis[r + 1][c]:
            nb.append((c, r + 1, ('U', r, c)))
        if r > 0 and not vis[r - 1][c]:
            nb.append((c, r - 1, ('U', r - 1, c)))
        if not nb:
            st.pop()
            continue
        n = nb[int(math.floor(rnd() * len(nb)))]
        k, i, j = n[2]
        (oR if k == 'R' else oU)[i][j] = 1
        vis[n[1]][n[0]] = 1
        st.append((n[0], n[1]))

    def nbrs(c, r):
        a = []
        if oR[r][c]:
            a.append(((c + 1) % cols, r))
        if oR[r][(c + cols - 1) % cols]:
            a.append(((c + cols - 1) % cols, r))
        if r < rows - 1 and oU[r][c]:
            a.append((c, r + 1))
        if r > 0 and oU[r - 1][c]:
            a.append((c, r - 1))
        return a
    dist = [[-1] * cols for _ in range(rows)]
    dist[0][0] = 0
    q = [(0, 0)]
    best, bd = (0, rows - 1), -1
    i = 0
    while i < len(q):
        c, r = q[i]
        i += 1
        if r == rows - 1 and dist[r][c] > bd:
            bd, best = dist[r][c], (c, r)
        for a, b in nbrs(c, r):
            if dist[b][a] < 0:
                dist[b][a] = dist[r][c] + 1
                q.append((a, b))
    W, HH = 2 * cols, 2 * rows + 1
    carve = [[False] * W for _ in range(HH)]
    carve[0][0] = True
    for r in range(rows):
        for c in range(cols):
            carve[2 * r + 1][2 * c] = True
            if oR[r][c]:
                carve[2 * r + 1][2 * c + 1] = True
            if r < rows - 1 and oU[r][c]:
                carve[2 * r + 2][2 * c] = True
    return {'carve': [''.join('1' if x else '0' for x in row) for row in carve],
            'goal': best, 'len': bd + 1}


def design(**kw):
    # ulazne vrijednosti (kao polja u HTML-u) -> svi parametri modela
    p = dict(DEFAULTS, **kw)
    H, D, pw, dp = max(p['H'], 20), max(p['D'], 15), max(p['pw'], 2), p['dp']
    R = D / 2.0
    tl = max(0.05, p['tl'] or 0.3)
    ext = max(0, p['pl'] or 0)
    cols = max(3, int(math.floor(math.pi * D / (2 * pw) + 0.5)))
    u = math.pi * D / (2 * cols)
    rows = max(2, int(math.floor((H / u - 1) / 2)))
    v = H / (2 * rows + 1)
    hw = min(u, v) / 2
    pr = max(0.6, hw - tl)
    dp = min(max(dp, pr + tl + ext), R * 0.45)
    cv = min(p['cv'], 2 * (R - dp - 1.2)) if p['cv'] > 0 else 0
    if cv < 3:
        cv = 0
    ct = min(p['ct'], H / 3.0)
    m = gen_maze(cols, rows, mulberry32(int(p['seed'])))
    cl, wl = p['cl'], p['wl']
    P = dict(seed=int(p['seed']), H=H, R=R, DP=dp, HW=hw, PR=pr, EXT=ext, CL=cl, TL=tl, WL=wl,
             RC=cv / 2.0, CT=ct, ZF=H - ct, W=2 * cols, HH=2 * rows + 1, GOAL_ROW=m['goal'][1],
             CARVE=m['carve'], cols=cols, rows=rows, solution_len=m['len'], PRINT_ORIENT=True)
    P['RS'] = R + cl
    P['RO'] = P['RS'] + wl
    P['LD'] = H + cl
    P['LT'] = P['LD'] + ct
    P['ZP'] = P['LD'] - (2 * P['GOAL_ROW'] + 1.5) * (H / P['HH'])
    return P


# ---------------- CadQuery ----------------
def build(P):
    import cadquery as cq
    H, R, DP, HW, PR, EXT = P['H'], P['R'], P['DP'], P['HW'], P['PR'], P['EXT']
    W, HH, CARVE = P['W'], P['HH'], P['CARVE']
    V = H / HH
    HWC = (HW ** 2 + DP ** 2) / (2.0 * DP)   # polumjer kruznog presjeka utora
    RCC = R + HWC - DP                         # radijus sredista presjeka

    def pt(r, a, z):
        return cq.Vector(r * math.cos(a), r * math.sin(a), z)

    def ang(x):
        return 2.0 * math.pi * (x + 0.5) / W

    def adiff(p, q):
        return (p - q + math.pi) % (2 * math.pi) - math.pi

    def arc_cutter(z, a0, a1):
        # pravi torus-sektor (revolve kruga oko osi Z) od kuta a0 do a1
        dr = a1 - a0
        d = math.degrees(dr)
        s = cq.Workplane('XZ').pushPoints([(RCC, z)]).circle(HWC).revolve(d, (0, 0, 0), (0, 1, 0))
        c = s.val().Center()
        if abs(adiff(math.atan2(c.y, c.x), -dr / 2.0)) < abs(adiff(math.atan2(c.y, c.x), dr / 2.0)):
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
        for s0, k in runs([carved(x, y) for x in range(W)]):
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
            a = pt(RCC, ang(x), (y + 0.5) * V)
            tools.append(cq.Workplane('XY').sphere(HWC).translate((a.x, a.y, a.z)).val())

    base = cq.Workplane('XY').circle(R).extrude(H)
    if P['RC'] > 0:
        base = base.cut(cq.Workplane('XY').circle(P['RC']).extrude(P['ZF']))
    shape = base.val()
    # rez jedan po jedan: cut(*tools) u jednom koraku daje nevaljanu geometriju
    # (degenerirana ploha, vrh s tolerancijom ~2.7 mm, rupe u STL-u)
    for t in tools:
        shape = shape.cut(t)
    if not shape.isValid():
        raise RuntimeError('jezgra nije valjano tijelo (isValid=False)')
    core = cq.Workplane('XY').newObject([shape])

    # ---- rukavac s pinom ----
    RS, RO, LD, LT, ZP = P['RS'], P['RO'], P['LD'], P['LT'], P['ZP']
    sleeve = cq.Workplane('XY').circle(RO).extrude(LT).cut(cq.Workplane('XY').circle(RS).extrude(LD))
    PCX = RS + 0.3 - EXT
    if abs(PCX - RS) < 0.02:   # ravna ploha kupole tocno na provrtu (EXT = 0.3) -> OCCT napravi 2 tijela
        PCX = RS - 0.02
    half = cq.Workplane('XY').box(2 * PR, 2 * PR, 2 * PR, centered=(False, True, True)).translate((-2 * PR, 0, 0))
    dome = cq.Workplane('XY').sphere(PR).intersect(half).translate((PCX, 0, ZP))
    # vrat pina uvijek ulazi do pola stijenke: bez njega se kod PCX ~ RS (EXT ~ 0.3)
    # ravna ploha kupole poklopi sa stijenkom i pin ispadne kao zasebno tijelo
    neck = cq.Solid.makeCylinder(PR, RS + P['WL'] / 2.0 - PCX, cq.Vector(PCX, 0, ZP), cq.Vector(1, 0, 0))
    pin = dome.union(cq.Workplane('XY').newObject([neck]))
    sleeve = sleeve.union(pin)
    for name, w in (('jezgra', core), ('rukavac', sleeve)):
        if not w.val().isValid() or len(w.val().Solids()) != 1:
            raise RuntimeError('%s: nevaljano ili vise tijela (%d)' % (name, len(w.val().Solids())))

    if P['PRINT_ORIENT']:   # otvorena strana gore
        core = core.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, H))
        sleeve = sleeve.rotate((0, 0, 0), (1, 0, 0), 180).translate((0, 0, LT))
    return core, sleeve


def export(P, out='.'):
    import cadquery as cq
    os.makedirs(out, exist_ok=True)
    core, sleeve = build(P)
    for name, obj in (('maze_core', core), ('maze_sleeve', sleeve)):
        cq.exporters.export(obj, os.path.join(out, name + '.step'))
        # tolerance = odstupanje od prave plohe (mm), angularTolerance u radijanima
        cq.exporters.export(obj, os.path.join(out, name + '.stl'), tolerance=0.01, angularTolerance=0.1)
    with open(os.path.join(out, 'maze_params.json'), 'w', encoding='utf-8') as f:
        json.dump(P, f, indent=2)
