# -*- coding: utf-8 -*-
# Maze puzzle (jezgra + rukavac) - CadQuery, izvozi STEP + STL + maze_params.json
# Pokretanje: python maze_cadquery.py [--seed 13305] [--D 40 --H 60 ...] [--out mapa]
# Polja su ista kao u HTML generatoru (tl = tolerancija pin-maze, cl = zracnost jezgra-rukavac).
import argparse

import maze_gen

ap = argparse.ArgumentParser()
for k, v in maze_gen.DEFAULTS.items():
    ap.add_argument('--' + k, type=type(v), default=13305 if k == 'seed' else v)
ap.add_argument('--out', default='.')
a = vars(ap.parse_args())
out = a.pop('out')

P = maze_gen.design(**a)
print('Mreza %d x %d, rjesenje %d celija; gradim ...' % (P['cols'], P['rows'], P['solution_len']))
maze_gen.export(P, out)
print('Gotovo: maze_core.step/.stl, maze_sleeve.step/.stl, maze_params.json -> %s' % out)
