#!/usr/bin/env python3
"""
Circuit-Symbol Stencil Ruler  -  3D-print generator  (faithful edition)
=======================================================================

Uses the ACTUAL symbol shapes drawn in `template_ruler.svg` (parsed by
svg_source.py) — 19 schematic symbols — and only rearranges / resizes them
into a tidy grid on a printable stencil plate.  The plate also carries an
engraved mm/cm measuring scale.

The symbols are cut clean through the plate as ~1.5 mm channels you trace
with a pen.  Any enclosed "island" (inside a triangle, gate body, circle,
rectangle, coil loop, output bubble, …) would drop out of a plain stencil,
so the generator automatically detects every island and ties it back to the
body with tiny **bridges** — solid uncut ties strong enough to survive a
print and normal handling.

Outputs:
  circuit_ruler_draft.png   - top-view draft (bridges highlighted)
  circuit_ruler.stl         - watertight solid for slicing / printing
"""

import numpy as np
import shapely.geometry as sg
from shapely.ops import unary_union, nearest_points
from shapely.affinity import translate, scale as shp_scale
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties

import svg_source

# ----------------------------------------------------------------------------
# parameters (millimetres)
# ----------------------------------------------------------------------------
COLS, ROWS = 5, 4
L = 190.0          # plate length  (X)
W = 118.0          # plate width   (Y)
T = 3.0            # plate thickness (Z)
CORNER = 4.0
MX = 7.0           # side margin
CM_STRIP = 12.0    # top strip: centimetre scale
IN_STRIP = 12.0    # bottom strip: inch scale
CELL_PAD = 5.0     # blank border kept inside each cell

CHANNEL = 1.5      # traced slot width
BRIDGE_W = 1.4     # island-tie width
ENGRAVE_DEPTH = 0.8
SCALE_MAX = 185    # last mm mark on the cm scale
SCALE_X0 = 6.0     # x of the 0 mark (shared by both scales)
INCH = 25.4

FONT = FontProperties(family="DejaVu Sans", weight="bold")

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def rrect(x0, y0, w, h, r):
    return sg.box(x0 + r, y0, x0 + w - r, y0 + h).union(
           sg.box(x0, y0 + r, x0 + w, y0 + h - r)).union(
           sg.Point(x0 + r,     y0 + r    ).buffer(r)).union(
           sg.Point(x0 + w - r, y0 + r    ).buffer(r)).union(
           sg.Point(x0 + r,     y0 + h - r).buffer(r)).union(
           sg.Point(x0 + w - r, y0 + h - r).buffer(r))

def text_poly(s, size, x, y, ha="center", va="center"):
    tp = TextPath((0, 0), s, size=size, prop=FONT)
    raw = [np.asarray(l) for l in tp.to_polygons(closed_only=True) if len(l) >= 3]
    keep = [(r, sg.Polygon(r).buffer(0)) for r in raw]
    keep = [(r, p) for r, p in keep if (not p.is_empty) and p.area > 1e-6]
    solids, holes = [], []
    for i, (ri, pi) in enumerate(keep):
        pt = sg.Point(ri[0])          # a vertex ON ring i (never inside its hole)
        depth = sum(1 for j, (rj, pj) in enumerate(keep)
                    if j != i and pj.contains(pt))
        (holes if depth % 2 else solids).append(pi)
    geom = unary_union(solids)
    if holes:
        geom = geom.difference(unary_union(holes))
    if geom.is_empty:
        return sg.Polygon()
    minx, miny, maxx, maxy = geom.bounds
    dx = x - {"left": minx, "center": (minx + maxx) / 2, "right": maxx}[ha]
    dy = y - {"bottom": miny, "center": (miny + maxy) / 2, "top": maxy}[va]
    return translate(geom, dx, dy)

def polylines_to_cut(polylines, width):
    return unary_union([sg.LineString(p).buffer(width / 2, cap_style=1,
                        join_style=1) for p in polylines if len(p) >= 2])

def components(geom):
    if geom.is_empty:
        return []
    return list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]

# ----------------------------------------------------------------------------
# bridges: tie every enclosed island back to the body
# ----------------------------------------------------------------------------
def add_bridges(plate, cut):
    """Return (bridges_union, n_islands). Bridges are solid ties to subtract
    from `cut` so nothing drops out of the stencil."""
    bridges = []
    for _ in range(10):
        active = cut.difference(unary_union(bridges)) if bridges else cut
        comps = components(plate.difference(active))
        if len(comps) <= 1:
            break
        main = max(comps, key=lambda p: p.area)
        islands = [p for p in comps if p is not main]
        for isl in islands:
            per = isl.exterior.length
            k = 1 if per < 10 else (2 if per < 34 else 3)
            for j in range(k):
                pt = isl.exterior.interpolate((j + 0.5) / k, normalized=True)
                near = nearest_points(main, pt)[0]        # across the channel
                seg = sg.LineString([(pt.x, pt.y), (near.x, near.y)])
                if seg.length < 1e-6:
                    continue
                # extend both ends so the tie fully bonds island <-> body
                v = np.array([near.x - pt.x, near.y - pt.y])
                v = v / (np.hypot(*v) + 1e-9) * 1.2
                seg = sg.LineString([(pt.x - v[0], pt.y - v[1]),
                                     (near.x + v[0], near.y + v[1])])
                bridges.append(seg.buffer(BRIDGE_W / 2, cap_style=2))
    return (unary_union(bridges) if bridges else sg.Polygon()), \
           len(components(plate.difference(cut))) - 1

# ----------------------------------------------------------------------------
# layout
# ----------------------------------------------------------------------------
def build_layout():
    body = rrect(0, 0, L, W, CORNER)
    syms = svg_source.symbols()

    gx0, gx1 = MX, L - MX
    gy0, gy1 = IN_STRIP, W - CM_STRIP
    cw = (gx1 - gx0) / COLS
    ch = (gy1 - gy0) / ROWS

    sym_cuts = []
    for idx, s in enumerate(syms):
        c, r = idx % COLS, idx // COLS
        cx = gx0 + cw * (c + 0.5)
        cy = gy1 - ch * (r + 0.5)
        f = min((cw - CELL_PAD) / s['w'], (ch - CELL_PAD) / s['h'])
        pls = [p * f + [cx, cy] for p in s['polylines']]
        sym_cuts.append(polylines_to_cut(pls, CHANNEL))
    through = unary_union(sym_cuts)

    # hanging hole (top-right, above the grid inside the scale strip corner)
    hang = sg.Point(L - 7, W - 6).buffer(2.6)
    through = unary_union([through, hang])

    bridges, n_isl = add_bridges(body, through)
    through_final = through.difference(bridges)

    # ---- engraved scales + title ----
    engrave = []

    # centimetre scale along the TOP edge (ticks point down)
    y_top = W
    for mm in range(0, SCALE_MAX + 1):
        x = SCALE_X0 + mm
        if x > L - 4:
            break
        tl, tw = (6.5, 0.5) if mm % 10 == 0 else \
                 (4.0, 0.45) if mm % 5 == 0 else (2.5, 0.4)
        engrave.append(sg.box(x - tw, y_top - tl, x + tw, y_top - 0.6))
        if mm % 10 == 0:
            engrave.append(text_poly(str(mm // 10), 3.0, x, y_top - tl - 2.3,
                                     va="top"))

    # inch scale along the BOTTOM edge (ticks point up), 1/8" subdivisions
    y_bot = 0.0
    n8 = int((L - 4 - SCALE_X0) / (INCH / 8))
    for k in range(0, n8 + 1):
        x = SCALE_X0 + k * (INCH / 8)
        if k % 8 == 0:   tl, tw = 6.5, 0.5     # whole inch
        elif k % 4 == 0: tl, tw = 4.5, 0.45    # 1/2"
        elif k % 2 == 0: tl, tw = 3.2, 0.4     # 1/4"
        else:            tl, tw = 2.1, 0.35    # 1/8"
        engrave.append(sg.box(x - tw, y_bot + 0.6, x + tw, y_bot + tl))
        if k % 8 == 0:
            engrave.append(text_poly(str(k // 8), 3.0, x, y_bot + tl + 2.3,
                                     va="bottom"))

    # title block in the empty bottom-right cell (carries the unit note)
    tcx = gx0 + cw * (COLS - 0.5)
    tcy = gy1 - ch * (ROWS - 0.5)
    lines = [("CIRCUIT", 3.6), ("STENCIL", 3.6), ("RULER", 3.6),
             ("cm  ·  in", 2.8)]
    y = tcy + 7.2
    for txt, sz in lines:
        engrave.append(text_poly(txt, sz, tcx, y, va="center"))
        y -= 4.6
    engrave = unary_union(engrave)

    print(f"symbols={len(syms)}  islands bridged={n_isl}  "
          f"bridges={len(components(bridges))}")
    return body, through_final, engrave, bridges

# ----------------------------------------------------------------------------
# PNG draft
# ----------------------------------------------------------------------------
def _poly_path(poly):
    from matplotlib.path import Path
    from shapely.geometry.polygon import orient
    poly = orient(poly, sign=1.0)
    verts, codes = [], []
    for ring in [poly.exterior, *poly.interiors]:
        xy = np.asarray(ring.coords)
        verts.extend(xy)
        codes.append(Path.MOVETO)
        codes.extend([Path.LINETO] * (len(xy) - 2))
        codes.append(Path.CLOSEPOLY)
    return Path(np.asarray(verts), codes)

def _draw(ax, geom, **kw):
    from matplotlib.patches import PathPatch
    for p in components(geom):
        if p.geom_type == "Polygon" and not p.is_empty:
            ax.add_patch(PathPatch(_poly_path(p), **kw))

def render_png(body, through, engrave, bridges, path, dpi=260, margin=3.0):
    # full-bleed: the plate fills the frame (no title / white borders) so the
    # image doesn't look shrunk when a browser scales it to fit.
    fw, fh = (L + 2 * margin) / 20.0, (W + 2 * margin) / 20.0
    fig = plt.figure(figsize=(fw, fh), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])                        # axes fill the figure
    plate = body.difference(through)
    _draw(ax, plate, facecolor="#2f6f8f", edgecolor="#12384a", linewidth=0.8, zorder=1)
    _draw(ax, engrave, facecolor="#bfe3f2", edgecolor="none", zorder=2)
    _draw(ax, bridges.intersection(plate), facecolor="none",
          edgecolor="#e8813a", linewidth=1.1, zorder=3)      # highlight ties
    ax.set_xlim(-margin, L + margin); ax.set_ylim(-margin, W + margin)
    ax.set_aspect("equal"); ax.axis("off")
    fig.savefig(path, dpi=dpi, facecolor="white", pad_inches=0)
    plt.close(fig)
    from PIL import Image
    print("wrote", path, Image.open(path).size)

# ----------------------------------------------------------------------------
# STL
# ----------------------------------------------------------------------------
def export_stl(body, through, engrave, path):
    import trimesh
    from trimesh.creation import extrude_polygon

    def clean(geom):
        out = []
        for p in components(geom):
            p = p.buffer(0)
            for q in components(p):
                if q.geom_type == "Polygon" and q.area > 0.02:
                    out.append(q)
        return out

    def solidify(m):
        m.merge_vertices(); m.update_faces(m.nondegenerate_faces())
        if not m.is_volume:
            m.fix_normals(); trimesh.repair.fill_holes(m)
        return m

    base = solidify(extrude_polygon(body, T))
    cuts = []
    for p in clean(through):
        m = solidify(extrude_polygon(p, T + 2.0)); m.apply_translation((0, 0, -1))
        if m.is_volume:
            cuts.append(m)
    for p in clean(engrave):
        m = solidify(extrude_polygon(p, ENGRAVE_DEPTH + 1.0))
        m.apply_translation((0, 0, T - ENGRAVE_DEPTH))
        if m.is_volume:
            cuts.append(m)
    print(f"boolean: base - {len(cuts)} cutters ...")
    res = trimesh.boolean.difference([base] + cuts, engine="manifold")
    res.merge_vertices()
    res.export(path)
    print(f"wrote {path}  watertight={res.is_watertight}  "
          f"vol={res.volume/1000:.1f} cm^3  tris={len(res.faces)}")
    return res

if __name__ == "__main__":
    import sys
    body, through, engrave, bridges = build_layout()
    render_png(body, through, engrave, bridges, "circuit_ruler_draft.png")
    if "--stl" in sys.argv:
        export_stl(body, through, engrave, "circuit_ruler.stl")
