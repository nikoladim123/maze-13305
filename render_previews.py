# -*- coding: utf-8 -*-
# Preview slike iz STL-ova (VTK, offscreen). Pokretanje: python render_previews.py [mapa]
# Izlaz u <mapa>/previews/: parts.png (naslovna), core.png, sleeve.png (presjek s pinom), assembled.png
import json
import os
import sys
import vtk

SIZE = (1600, 1200)   # 4:3
CORE_COL = (0.95, 0.55, 0.15)
SLEEVE_COL = (0.25, 0.45, 0.85)
P = None
OUT = None


def load(path):
    r = vtk.vtkSTLReader()
    r.SetFileName(path)
    r.Update()
    return r.GetOutput()


def to_work(poly, z_top):
    # STL-ovi su u orijentaciji za print (180 oko X); vrati u radnu: ulaz labirinta dolje
    t = vtk.vtkTransform()
    if P['PRINT_ORIENT']:
        t.Translate(0, 0, z_top)
        t.RotateX(180)
    f = vtk.vtkTransformPolyDataFilter()
    f.SetInputData(poly)
    f.SetTransform(t)
    f.Update()
    return f.GetOutput()


def half(poly, normal):
    # presjek ravninom kroz os Z; ostaje strana u smjeru normale
    pl = vtk.vtkPlane()
    pl.SetOrigin(0, 0, 0)
    pl.SetNormal(*normal)
    c = vtk.vtkClipPolyData()
    c.SetInputData(poly)
    c.SetClipFunction(pl)
    c.Update()
    return c.GetOutput()


def actor(poly, color, pos=(0, 0, 0), opacity=1.0):
    n = vtk.vtkPolyDataNormals()   # glatko sjencanje, ostri rubovi ostaju
    n.SetInputData(poly)
    n.SetFeatureAngle(35)
    n.Update()
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(n.GetOutputPort())
    a = vtk.vtkActor()
    a.SetMapper(m)
    p = a.GetProperty()
    p.SetColor(*color)
    p.SetSpecular(0.25)
    p.SetSpecularPower(30)
    p.SetOpacity(opacity)
    p.BackfaceCullingOff()
    a.SetPosition(*pos)
    return a


def render(actors, fname, view_dir=(0, -1, 0), elev=15, azim=0, zoom=1.0):
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    ren.SetBackground2(0.82, 0.86, 0.92)
    ren.GradientBackgroundOn()
    ren.SetUseDepthPeeling(1)
    ren.SetMaximumNumberOfPeels(20)
    for a in actors:
        ren.AddActor(a)
    cam = ren.GetActiveCamera()
    cam.SetFocalPoint(0, 0, 0)
    cam.SetPosition(*(-v for v in view_dir))
    cam.SetViewUp(0, 0, 1)
    cam.SetViewAngle(18)          # blaga perspektiva
    cam.Azimuth(azim)
    cam.Elevation(elev)
    cam.OrthogonalizeViewUp()
    ren.ResetCamera()
    cam.Zoom(zoom)
    ren.ResetCameraClippingRange()

    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetAlphaBitPlanes(1)
    win.SetMultiSamples(0)        # depth peeling ne radi s MSAA
    win.SetSize(*SIZE)
    win.AddRenderer(ren)
    win.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.SetScale(1)
    w2i.ReadFrontBufferOff()
    w2i.Update()
    wr = vtk.vtkPNGWriter()
    wr.SetFileName(os.path.join(OUT, fname))
    wr.SetInputConnection(w2i.GetOutputPort())
    wr.Write()
    print('  ' + os.path.join(OUT, fname))


def goal_angle():
    # red utora u kojem pin stoji kad je kutija zatvorena (ZP u rukavcu); uzmi slijepi kraj u tom redu
    W, V = P['W'], P['H'] / P['HH']
    y = round((P['LD'] - P['ZP']) / V - 0.5)
    c = lambda x, yy: 0 <= yy < P['HH'] and P['CARVE'][yy][x % W] == '1'
    xs = [x for x in range(W) if c(x, y)]
    ends = [x for x in xs if c(x - 1, y) + c(x + 1, y) + c(x, y - 1) + c(x, y + 1) == 1]
    x = (ends or xs)[0]
    return 360.0 * (x + 0.5) / W


def assembled(core_work):
    # jezgra ulazi u rukavac okrenuta: z=0 jezgre (ulaz + supljina) ide prema poklopcu
    t = vtk.vtkTransform()
    t.PostMultiply()
    t.RotateX(180)
    t.Translate(0, 0, P['LD'])
    t.RotateZ(goal_angle())   # pin (na +X) u utoru ciljnog reda
    f = vtk.vtkTransformPolyDataFilter()
    f.SetInputData(core_work)
    f.SetTransform(t)
    f.Update()
    return f.GetOutput()


def render_all(d='.', core_col=CORE_COL, sleeve_col=SLEEVE_COL):
    global P, OUT
    P = json.load(open(os.path.join(d, 'maze_params.json'), encoding='utf-8'))
    OUT = os.path.join(d, 'previews')
    os.makedirs(OUT, exist_ok=True)
    core = to_work(load(os.path.join(d, 'maze_core.stl')), P['H'])
    sleeve = to_work(load(os.path.join(d, 'maze_sleeve.stl')), P['LT'])
    gap = 2 * P['RO'] + 12

    print('Renderam:')
    # naslovna: oba dijela jedan do drugog
    render([actor(core, core_col, (-gap / 2, 0, 0)),
            actor(sleeve, sleeve_col, (gap / 2, 0, 0))], 'parts.png', elev=12, zoom=1.1)
    render([actor(core, core_col)], 'core.png', elev=12, azim=-30, zoom=1.0)
    # rukavac prerezan kroz os, gledamo u straznju stijenku na kojoj je pin (+X)
    render([actor(half(sleeve, (1, 0, 0)), sleeve_col)], 'sleeve.png',
           view_dir=(1, 0, 0), elev=10, azim=-25, zoom=1.0)
    # sastavljeno (zatvoreno): rukavac poluproziran, gledamo prema pinu
    render([actor(assembled(core), core_col),
            actor(sleeve, sleeve_col, opacity=0.3)], 'assembled.png',
           view_dir=(-1, 0, 0), elev=12, azim=-20, zoom=1.0)


if __name__ == '__main__':
    render_all(sys.argv[1] if len(sys.argv) > 1 else '.')
