# Cylindrical Maze Puzzle Box generator

Parametric cylindrical maze puzzles: a core (optionally hollow, as a gift box) with a maze
cut into its surface, and a sleeve with a pin on the inside. Every design is generated from
a seed, and the same seed and parameters always give the same maze.

| File | Content |
| --- | --- |
| `maze_gen.py` | maze generator + CadQuery model (STEP, STL, `maze_params.json`) |
| `maze_cadquery.py` | CLI: `python maze_cadquery.py --seed 13305 --D 40 --H 60 --out dir` |
| `render_previews.py` | preview images (VTK): `python render_previews.py dir` |
| `cults_upload.py` | manual publishing of one design to Cults3D |
| `auto_publish.py` | automatic publishing (see below) |

Model files are not kept in this repository. For each Cults upload they are pushed to a
temporary branch, and the branch is deleted once Cults has downloaded them.

## Automatic publishing

`python auto_publish.py tick` runs every 10 minutes (Windows Task Scheduler):

- plans 5-8 uploads per day at random times (07:00-23:30, at least 45 min apart);
- generates a random design (pin tolerance 0.2 mm), checks that both bodies are valid
  and the STL meshes are closed, renders previews;
- pushes it to a temporary branch, publishes it on Cults3D for free (`cults_pu`),
  deletes the branch once Cults has the files;
- sets the price to 0.50 EUR once a design reaches 5 downloads
  (only designs published by this script, tracked in `auto_state.json`);
- pauses after 3 failed uploads in a row (`python auto_publish.py resume`).

Other commands: `publish` (one now), `check`, `status`, `pause` / `resume`. Log: `logs/auto_publish.log`.
Requires `CULTS_USER` and `CULTS_API_KEY` environment variables.

```
pip install cadquery vtk requests truststore
```
