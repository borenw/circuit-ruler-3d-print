#!/usr/bin/env python3
"""
Faithful parser for template_ruler.svg.

The source is a flat list of <path>/<rect> elements, each with its own
`transform="matrix(...)"`.  Paths use only absolute M / L / C / Z.  We flatten
cubic beziers, apply each element's matrix, and return absolute-coordinate
polylines plus the effective (transformed) stroke width — so the real drawn
shapes can be reproduced exactly, then arranged/sized onto the ruler.
"""
import re
import numpy as np
import shapely.geometry as sg

NUM = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?')

def _matrix(s):
    if not s:
        return (1, 0, 0, 1, 0, 0)
    m = re.search(r'matrix\(([^)]*)\)', s)
    if not m:
        return (1, 0, 0, 1, 0, 0)
    return tuple(float(x) for x in NUM.findall(m.group(1)))[:6]

def _apply(mat, x, y):
    a, b, c, d, e, f = mat
    return (a * x + c * y + e, b * x + d * y + f)

def _bezier(p0, p1, p2, p3, n=18):
    t = np.linspace(0, 1, n)[:, None]
    mt = 1 - t
    return (mt**3 * p0 + 3 * mt**2 * t * p1 + 3 * mt * t**2 * p2 + t**3 * p3)

def _parse_d(d):
    """return list of subpaths (each a list of (x,y)) in the path's local space."""
    toks = re.findall(r'[MLCZ]|' + NUM.pattern, d)
    subs, cur, i, cx, cy, start = [], [], 0, 0.0, 0.0, None
    def nf(k):
        return [float(toks[k + j]) for j in range(0)]
    while i < len(toks):
        t = toks[i]
        if t == 'M':
            if cur:
                subs.append(cur)
            cx, cy = float(toks[i+1]), float(toks[i+2]); i += 3
            cur = [(cx, cy)]; start = (cx, cy)
            # implicit L pairs following M
            while i < len(toks) and toks[i] not in 'MLCZ':
                cx, cy = float(toks[i]), float(toks[i+1]); i += 2
                cur.append((cx, cy))
        elif t == 'L':
            i += 1
            while i < len(toks) and toks[i] not in 'MLCZ':
                cx, cy = float(toks[i]), float(toks[i+1]); i += 2
                cur.append((cx, cy))
        elif t == 'C':
            i += 1
            while i < len(toks) and toks[i] not in 'MLCZ':
                p0 = np.array([cx, cy])
                p1 = np.array([float(toks[i]),   float(toks[i+1])])
                p2 = np.array([float(toks[i+2]), float(toks[i+3])])
                p3 = np.array([float(toks[i+4]), float(toks[i+5])]); i += 6
                for pt in _bezier(p0, p1, p2, p3)[1:]:
                    cur.append((pt[0], pt[1]))
                cx, cy = p3
        elif t == 'Z':
            i += 1
            if start:
                cur.append(start)
        else:
            i += 1
    if cur:
        subs.append(cur)
    return subs

def parse(path="template_ruler.svg"):
    svg = open(path).read()
    elems = []
    for tag in re.findall(r'<(?:path|rect)\b[^>]*/?>', svg):
        mat = _matrix(re.search(r'transform="([^"]*)"', tag).group(1)
                      if 'transform="' in tag else '')
        a, b, c, d, e, f = mat
        sc = (abs(a * d - b * c)) ** 0.5 or 1.0
        swm = re.search(r'stroke-width="([\d.]+)"', tag)
        sw = float(swm.group(1)) if swm else 6.0
        fillm = re.search(r'fill="([^"]*)"', tag)
        fill = fillm.group(1) if fillm else 'none'
        grpm = re.search(r'data-group="([^"]*)"', tag)
        grp = grpm.group(1) if grpm else ''
        if tag.startswith('<rect'):
            g = {k: float(re.search(k + r'="([\d.\-]+)"', tag).group(1))
                 for k in ('x', 'y', 'width', 'height')}
            x0, y0, w, h = g['x'], g['y'], g['width'], g['height']
            local = [[(x0, y0), (x0+w, y0), (x0+w, y0+h), (x0, y0+h), (x0, y0)]]
        else:
            dm = re.search(r'\bd="([^"]*)"', tag)
            if not dm:
                continue
            local = _parse_d(dm.group(1))
        subs = [[_apply(mat, x, y) for (x, y) in sp] for sp in local]
        subs = [np.array(sp) for sp in subs if len(sp) >= 2]
        if not subs:
            continue
        elems.append(dict(subs=subs, w=sw * sc, fill=fill, group=grp))
    return elems

def bounds(elems):
    allp = np.vstack([sp for el in elems for sp in el['subs']])
    return allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max()

def _is_straight(p):
    if len(p) <= 2:
        return True
    d = p[-1] - p[0]
    Ln = np.hypot(*d)
    if Ln < 1e-9:
        return False
    n = np.array([-d[1], d[0]]) / Ln
    return np.abs((p[1:-1] - p[0]) @ n).max() < 0.06 * Ln

def _trim_leads(pls, lead_frac=0.22, cap_frac=0.30):
    """Shorten long straight terminal leads so scaling is driven by the symbol
    BODY, not its wires.  Faithful: only wire length changes, not the shapes.

    A stroke counts as a lead only if it is straight, long, AND runs parallel to
    the symbol's long axis — so plates, bars and switch levers (which cross the
    axis) are kept as body, not mistaken for wires."""
    allp = np.vstack(pls)
    ex, ey = np.ptp(allp[:, 0]), np.ptp(allp[:, 1])
    span = max(ex, ey)
    axis = np.array([1.0, 0.0]) if ex >= ey else np.array([0.0, 1.0])
    long_th = lead_frac * span
    body = []
    for p in pls:
        seglen = np.hypot(*np.diff(p, axis=0).T).sum()
        d = p[-1] - p[0]
        dl = np.hypot(*d)
        parallel = dl > 1e-9 and abs((d / dl) @ axis) > 0.94
        if _is_straight(p) and seglen > long_th and parallel:
            continue                          # a lead — drop from body estimate
        body.append(p)
    if not body:
        return pls
    bx = np.vstack(body)
    x0, y0, x1, y1 = bx[:, 0].min(), bx[:, 1].min(), bx[:, 0].max(), bx[:, 1].max()
    if max(x1 - x0, y1 - y0) < 0.12 * span:   # near-total collapse -> don't risk it
        return pls
    m = cap_frac * max(x1 - x0, y1 - y0)      # keep short lead stubs
    box = sg.box(x0 - m, y0 - m, x1 + m, y1 + m)
    out = []
    for p in pls:
        inter = sg.LineString(p).intersection(box)
        if inter.is_empty:
            continue
        gs = inter.geoms if inter.geom_type.startswith("Multi") else [inter]
        for g in gs:
            if g.geom_type == "LineString" and g.length > 1e-6:
                out.append(np.asarray(g.coords))
    return out or pls

def symbols(path="template_ruler.svg", D=12):
    """Segment the drawing into individual symbols (spatial clusters).

    Returns a reading-ordered list of dicts, each with:
      polylines : list of Nx2 arrays, centred on the symbol's bbox centre,
                  y flipped so the symbol is upright (y-up)
      w, h      : symbol width / height in SVG units
      sx, sy    : original centre (y-up) — used only for ordering
    """
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    els = parse(path)
    geoms = [unary_union([LineString(sp).buffer(max(el['w'] / 2, 3.0))
                          for sp in el['subs']]) for el in els]
    merged = unary_union([g.buffer(D) for g in geoms])
    comps = list(merged.geoms) if merged.geom_type.startswith("Multi") else [merged]
    groups = [[] for _ in comps]
    for el, g in zip(els, geoms):
        p = g.representative_point()
        for i, c in enumerate(comps):
            if c.contains(p):
                groups[i].append(el)
                break
    syms = []
    for grp in groups:
        pls = []
        for el in grp:
            for sp in el['subs']:
                arr = np.array(sp, float)
                arr[:, 1] *= -1                      # flip y-up
                pls.append(arr)
        pls = _trim_leads(pls)
        allp = np.vstack(pls)
        cx = (allp[:, 0].min() + allp[:, 0].max()) / 2
        cy = (allp[:, 1].min() + allp[:, 1].max()) / 2
        syms.append(dict(polylines=[p - [cx, cy] for p in pls],
                         w=allp[:, 0].max() - allp[:, 0].min(),
                         h=allp[:, 1].max() - allp[:, 1].min(),
                         sx=cx, sy=cy))
    # reading order: top rows first (larger y), then left→right
    syms.sort(key=lambda s: (-round(s['sy'] / 250.0), s['sx']))
    return syms

if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    els = parse()
    x0, y0, x1, y1 = bounds(els)
    print(f"{len(els)} elements   bbox=({x0:.0f},{y0:.0f})..({x1:.0f},{y1:.0f})"
          f"   size={x1-x0:.0f} x {y1-y0:.0f}")
    fig, ax = plt.subplots(figsize=(16, 7), dpi=130)
    for el in els:
        for sp in el['subs']:
            ax.plot(sp[:, 0], -sp[:, 1], '-', color='#123',
                    lw=max(0.6, el['w'] * 0.05))
    ax.set_aspect('equal'); ax.axis('off')
    ax.set_title("template_ruler.svg — faithful parse (y flipped for view)")
    fig.tight_layout(); fig.savefig("_svg_faithful.png", facecolor='white')
    print("wrote _svg_faithful.png")
