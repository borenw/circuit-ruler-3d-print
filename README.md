# Circuit Stencil Ruler — 3D Print

A printable circuit-drafting **stencil ruler**. One flat plate gives you:

- an engraved **mm / cm measuring scale** along the top edge (0–170 mm)
- **11 through-cut schematic symbols** you trace with a pen
  (resistor ×2, capacitor, inductor, diode, battery, ground, switch, AC source, lamp, NPN transistor)
- a **node/junction dot** hole
- engraved symbol labels + a title block
- a hanging hole

![draft render](circuit_ruler_draft.png)

The symbols are the same family sketched in [`template_ruler.svg`](template_ruler.svg),
the original hand-drawn artwork this stencil is derived from.

## Files

| File | What it is |
|------|-----------|
| `circuit_ruler.stl` | **The 3D print file.** 180 × 72 × 3 mm, watertight solid. |
| `circuit_ruler_draft.png` | Top-view draft render (review before printing). |
| `circuit_ruler.py` | Parametric generator (edit dimensions / symbols, re-run). |
| `template_ruler.svg` | Original hand-drawn source artwork. |

## Print settings

- **Size:** 180 × 72 × 3 mm — fits any bed ≥ 200 × 100 mm.
- **Material:** PLA or PETG.
- **Layer height:** 0.16–0.20 mm.
- **Walls / perimeters:** 3+ (the plate is only 3 mm — perimeters give it stiffness).
- **Infill:** 30–100% (thin part, so it barely matters).
- **Supports:** none. It is a flat plate; symbol slots and the engraved scale
  print top-down with no overhangs.
- **Orientation:** flat on the bed, engraved face up.

The symbol channels are **1.5 mm wide** — trace them with a fine pen or a
0.5–0.7 mm mechanical pencil. The engraved scale is **0.8 mm deep**.

## Regenerating / customizing

Requires Python 3 with `numpy`, `shapely`, `trimesh`, `manifold3d`,
`mapbox_earcut`, and `matplotlib`.

```bash
python3 circuit_ruler.py          # draft PNG only
python3 circuit_ruler.py --stl    # draft PNG + STL
```

Tune the constants at the top of `circuit_ruler.py` (`L`, `W`, `T`, `SW`,
`ENGRAVE_DEPTH`, the `SYMBOLS` list) to change the plate size, slot width,
engrave depth, or which symbols appear.

## License

CC BY 4.0 — free to print, share, and remix with attribution.
