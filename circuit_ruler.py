#!/usr/bin/env python3
"""
Circuit-Symbol Stencil Ruler  -  3D-print generator
====================================================

Generates a printable circuit-drafting stencil ruler from a clean parametric
definition (mm units).  The plate carries:

  * an engraved mm / cm measuring scale along the top edge (0..170 mm)
  * a grid of THROUGH-CUT circuit symbols you trace with a pen
    (R, R-box, C, L, diode, battery, ground, switch, AC source, lamp, NPN)
  * engraved symbol labels + a title block
  * a hanging hole

Outputs:
  circuit_ruler_draft.png   - top-view draft render (review before printing)
  circuit_ruler.stl         - watertight solid for slicing / 3D printing

The source artwork (template_ruler.svg, a hand-sketched version of the same
symbol family) is kept in the repo for reference.
"""

import numpy as np
import shapely.geometry as sg
from shapely.ops import unary_union
from shapely.affinity import translate, rotate, scale as shp_scale
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPoly
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties

# ----------------------------------------------------------------------------
# Global parameters (millimetres)
# ----------------------------------------------------------------------------
L      = 180.0     # plate length  (X)
W      = 72.0      # plate width   (Y)
T      = 3.0       # plate thickness (Z)
CORNER = 4.0       # rounded corner radius
SW     = 1.5       # symbol channel width (traceable slot)
ENGRAVE_DEPTH = 0.8   # depth of engraved scale / text
DOT_R  = 1.6       # junction-node hole radius

SCALE_STRIP = 12.0   # height of top ruler strip
SCALE_MAX   = 170    # last labelled mm mark
SCALE_X0    = 5.0    # x of the 0-mm mark (left margin)

FONT = FontProperties(family="DejaVu Sans", weight="bold")

# ----------------------------------------------------------------------------
# geometry helpers
# ----------------------------------------------------------------------------
def rounded_rect(x0, y0, w, h, r):
    return sg.box(x0, y0, x0 + w, y0 + h).buffer(-0.0).buffer(0)  # placeholder

def rrect(x0, y0, w, h, r):
    """axis-aligned rounded rectangle as a polygon"""
    return sg.box(x0 + r, y0, x0 + w - r, y0 + h).union(
           sg.box(x0, y0 + r, x0 + w, y0 + h - r)).union(
           sg.Point(x0 + r,     y0 + r    ).buffer(r)).union(
           sg.Point(x0 + w - r, y0 + r    ).buffer(r)).union(
           sg.Point(x0 + r,     y0 + h - r).buffer(r)).union(
           sg.Point(x0 + w - r, y0 + h - r).buffer(r))

def strokes(polylines, width=SW):
    """turn a list of point-lists into a filled 'ink' region (rounded caps)."""
    parts = []
    for pl in polylines:
        if len(pl) == 1:
            parts.append(sg.Point(pl[0]).buffer(width / 2))
        else:
            parts.append(sg.LineString(pl).buffer(width / 2,
                          cap_style=1, join_style=1))
    return unary_union(parts)

def arc(cx, cy, r, a0, a1, n=24):
    a = np.linspace(np.radians(a0), np.radians(a1), n)
    return list(zip(cx + r * np.cos(a), cy + r * np.sin(a)))

def text_poly(s, size, x, y, ha="center", va="center"):
    """filled outline of text as a valid shapely geometry (letter holes handled
    by even-odd containment depth, so results extrude to watertight solids)."""
    tp = TextPath((0, 0), s, size=size, prop=FONT)
    loops = [sg.Polygon(l).buffer(0) for l in tp.to_polygons(closed_only=True)
             if len(l) >= 3]
    loops = [p for p in loops if (not p.is_empty) and p.area > 1e-6]
    solids, holes = [], []
    for i, p in enumerate(loops):
        pt = p.representative_point()
        depth = sum(1 for j, q in enumerate(loops)
                    if j != i and q.contains(pt))
        (holes if depth % 2 else solids).append(p)
    geom = unary_union(solids)
    if holes:
        geom = geom.difference(unary_union(holes))
    if geom.is_empty:
        return sg.Polygon()
    minx, miny, maxx, maxy = geom.bounds
    dx = x - {"left": minx, "center": (minx + maxx) / 2, "right": maxx}[ha]
    dy = y - {"bottom": miny, "center": (miny + maxy) / 2, "top": maxy}[va]
    return translate(geom, dx, dy)

# ----------------------------------------------------------------------------
# circuit symbols  (local coords, centred at 0,0, ~26 wide x 14 tall)
#   returns (ink_geometry, [extra node-dot centres])
# ----------------------------------------------------------------------------
LEAD = 13.0   # half length of a symbol's horizontal leads

def sym_resistor_zig():
    p = [(-LEAD, 0), (-7, 0)]
    xs = np.linspace(-7, 7, 9)
    for i, xv in enumerate(xs[1:-1]):
        p.append((xv, 4 if i % 2 == 0 else -4))
    p += [(7, 0), (LEAD, 0)]
    return strokes([p]), []

def sym_resistor_box():
    leads = [[(-LEAD, 0), (-8, 0)], [(8, 0), (LEAD, 0)]]
    box = [(-8, -4), (8, -4), (8, 4), (-8, 4), (-8, -4)]
    return strokes(leads + [box]), []

def sym_capacitor():
    return strokes([
        [(-LEAD, 0), (-2, 0)], [(-2, -6), (-2, 6)],
        [(2, -6), (2, 6)],     [(2, 0), (LEAD, 0)],
    ]), []

def sym_inductor():
    parts = [[(-LEAD, 0), (-8, 0)], [(8, 0), (LEAD, 0)]]
    for cx in (-6, -2, 2, 6):
        parts.append(arc(cx, 0, 2, 0, 180))
    return strokes(parts), []

def sym_diode():
    tri = [(-4, -5), (-4, 5), (4, 0), (-4, -5)]
    return strokes([
        [(-LEAD, 0), (-4, 0)], tri,
        [(4, -5), (4, 5)], [(4, 0), (LEAD, 0)],
    ]), []

def sym_battery():
    return strokes([
        [(-LEAD, 0), (-6, 0)],
        [(-6, -6), (-6, 6)], [(-3, -3), (-3, 3)],
        [(1, -6), (1, 6)],   [(4, -3), (4, 3)],
        [(4, 0), (LEAD, 0)],
    ]), []

def sym_ground():
    return strokes([
        [(0, 7), (0, 0)],
        [(-6, 0), (6, 0)], [(-4, -3), (4, -3)], [(-2, -6), (2, -6)],
    ]), []

def sym_switch():
    ink = strokes([
        [(-LEAD, 0), (-7, 0)],
        [(-7, 0), (6, 6)],
        [(7, 0), (LEAD, 0)],
    ])
    return ink, [(-7, 0), (7, 0)]

def sym_ac_source():
    circ = arc(0, 0, 7, 0, 360)
    sine = [(x, 3.2 * np.sin(np.radians(x * 40)))
            for x in np.linspace(-4.5, 4.5, 30)]
    return strokes([
        [(-LEAD, 0), (-7, 0)], [(7, 0), (LEAD, 0)],
        circ, sine,
    ]), []

def sym_lamp():
    circ = arc(0, 0, 7, 0, 360)
    d = 7 / np.sqrt(2)
    return strokes([
        [(-LEAD, 0), (-7, 0)], [(7, 0), (LEAD, 0)],
        circ, [(-d, -d), (d, d)], [(-d, d), (d, -d)],
    ]), []

def sym_npn():
    circ = arc(0, 0, 8, 0, 360)
    base = [[(-LEAD, 0), (-3, 0)], [(-3, -4.5), (-3, 4.5)]]
    coll = [[(-3, 2.5), (4.5, 6.5)], [(4.5, 6.5), (4.5, 11)]]
    emit = [[(-3, -2.5), (4.5, -6.5)], [(4.5, -6.5), (4.5, -11)]]
    arrow = [[(4.5, -6.5), (2.0, -6.0)], [(4.5, -6.5), (3.8, -3.9)]]
    return strokes([circ] + base + coll + emit + arrow), []

SYMBOLS = [
    ("Resistor",   sym_resistor_zig),
    ("Resistor",   sym_resistor_box),
    ("Capacitor",  sym_capacitor),
    ("Inductor",   sym_inductor),
    ("Diode",      sym_diode),
    ("Battery",    sym_battery),
    ("Ground",     sym_ground),
    ("Switch",     sym_switch),
    ("AC Source",  sym_ac_source),
    ("Lamp",       sym_lamp),
    ("NPN",        sym_npn),
    ("Node",       None),          # special: single dot hole
]

# ----------------------------------------------------------------------------
# build the full 2D layout -> lists of shapely geoms
# ----------------------------------------------------------------------------
def build_layout():
    body = rrect(0, 0, L, W, CORNER)

    through = []     # full-depth cutouts (symbols, node dots, hang hole)
    engrave = []     # shallow recesses (scale, labels, title)

    # ---- hanging hole (top-right corner) ----
    through.append(sg.Point(L - 7, W - 6).buffer(2.6))

    # ---- measuring scale along top edge ----
    y_top = W
    for mm in range(0, SCALE_MAX + 1):
        x = SCALE_X0 + mm
        if x > L - 4:
            break
        if mm % 10 == 0:
            tick_len, tw = 6.5, 0.5
        elif mm % 5 == 0:
            tick_len, tw = 4.0, 0.45
        else:
            tick_len, tw = 2.5, 0.4
        engrave.append(sg.box(x - tw, y_top - tick_len, x + tw, y_top - 0.6))
        if mm % 10 == 0:
            engrave.append(text_poly(str(mm // 10), 3.0, x,
                                     y_top - tick_len - 2.4, va="top"))
    # "cm" unit tag
    engrave.append(text_poly("cm", 3.0, SCALE_X0 + SCALE_MAX + 3,
                             y_top - 4.5, ha="left", va="center"))

    # ---- symbol grid ----
    cols, rows = 4, 3
    gx0 = 6.0
    title_h = 8.0                       # bottom strip reserved for title
    gy0 = title_h + 1.0
    gw = L - 2 * gx0
    gh = (W - SCALE_STRIP) - gy0 - 1.0
    cw, ch = gw / cols, gh / rows
    label_band = 4.0
    for idx, (name, fn) in enumerate(SYMBOLS):
        c = idx % cols
        r = idx // cols
        cx = gx0 + cw * (c + 0.5)
        cell_bottom = gy0 + ch * (rows - 1 - r)
        sym_cy = cell_bottom + label_band + (ch - label_band) / 2
        if fn is None:                       # node dot
            through.append(sg.Point(cx, sym_cy).buffer(DOT_R))
        else:
            ink, dots = fn()
            minx, miny, maxx, maxy = ink.bounds
            fx = (cw - 5.0) / (maxx - minx)
            fy = (ch - label_band - 2.0) / (maxy - miny)
            f = min(fx, fy, 1.0)
            ink = shp_scale(ink, f, f, origin=(0, 0))
            ink = translate(ink, cx, sym_cy)
            through.append(ink)
            for dx, dy in dots:
                through.append(sg.Point(cx + dx * f,
                                        sym_cy + dy * f).buffer(DOT_R * 0.8))
        engrave.append(text_poly(name, 2.6, cx, cell_bottom + 1.0, va="bottom"))

    # ---- title block ----
    engrave.append(text_poly("CIRCUIT  STENCIL  RULER", 4.4, L / 2, 1.8,
                             va="bottom"))

    return body, unary_union(through), unary_union(engrave)


# ----------------------------------------------------------------------------
# PNG draft
# ----------------------------------------------------------------------------
def _poly_path(poly):
    """matplotlib Path for a shapely Polygon, holes as true holes (nonzero)."""
    from matplotlib.path import Path
    from shapely.geometry.polygon import orient
    poly = orient(poly, sign=1.0)          # exterior CCW, interiors CW
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
    if geom.is_empty:
        return
    polys = geom.geoms if geom.geom_type.startswith("Multi") else [geom]
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        ax.add_patch(PathPatch(_poly_path(p), **kw))

def render_png(body, through, engrave, path):
    fig, ax = plt.subplots(figsize=(L / 25.4, (W + 18) / 25.4), dpi=200)
    plate = body.difference(through)
    _draw(ax, plate, facecolor="#2f6f8f", edgecolor="#12384a",
          linewidth=1.0, zorder=1)
    _draw(ax, engrave, facecolor="#bfe3f2", edgecolor="none", zorder=2)
    ax.set_xlim(-6, L + 6)
    ax.set_ylim(-6, W + 12)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Circuit Stencil Ruler  —  print draft   "
                 f"({L:.0f} × {W:.0f} × {T:.0f} mm)",
                 fontsize=9, color="#12384a", pad=6)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# ----------------------------------------------------------------------------
# STL export
# ----------------------------------------------------------------------------
def export_stl(body, through, engrave, path):
    import trimesh
    from trimesh.creation import extrude_polygon

    def polys(geom):
        if geom.is_empty:
            return []
        gg = list(geom.geoms) if geom.geom_type.startswith("Multi") else [geom]
        out = []
        for p in gg:
            p = p.buffer(0)
            if p.is_empty:
                continue
            out += list(p.geoms) if p.geom_type.startswith("Multi") else [p]
        return [p for p in out if p.geom_type == "Polygon" and p.area > 0.02]

    def solidify(m):
        m.merge_vertices()
        m.update_faces(m.nondegenerate_faces())
        if not m.is_volume:
            m.fix_normals()
            trimesh.repair.fill_holes(m)
        return m

    base = solidify(extrude_polygon(body, T))

    cuts, bad = [], 0
    for p in polys(through):
        m = extrude_polygon(p, T + 2.0)
        m.apply_translation((0, 0, -1.0))            # through the whole plate
        m = solidify(m)
        if m.is_volume:
            cuts.append(m)
        else:
            bad += 1
    for p in polys(engrave):
        m = extrude_polygon(p, ENGRAVE_DEPTH + 1.0)
        m.apply_translation((0, 0, T - ENGRAVE_DEPTH))  # recess top face
        m = solidify(m)
        if m.is_volume:
            cuts.append(m)
        else:
            bad += 1

    print(f"boolean: base - {len(cuts)} cutters ({bad} skipped non-volume) ...")
    result = trimesh.boolean.difference([base] + cuts, engine="manifold")
    result.merge_vertices()
    result.export(path)
    print(f"wrote {path}  watertight={result.is_watertight}  "
          f"vol={result.volume/1000:.1f} cm^3  tris={len(result.faces)}")
    return result


if __name__ == "__main__":
    import sys
    body, through, engrave = build_layout()
    render_png(body, through, engrave, "circuit_ruler_draft.png")
    if "--stl" in sys.argv:
        export_stl(body, through, engrave, "circuit_ruler.stl")
