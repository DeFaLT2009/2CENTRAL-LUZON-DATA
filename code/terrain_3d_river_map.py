"""
terrain_3d_river_map.py
=======================
Stage 9 of the pipeline.

IMPORTANT - PROVENANCE / NO-FABRICATION RULE
-------------------------------------------
No Digital Elevation Model (SRTM, ASTER, CARTOSAT, LiDAR) is present in the
repository and the sandbox cannot reach a geospatial data host.  There is
**no bathymetry** for the rivers either.

Consequently this script does NOT claim real elevation or water depth.  It
constructs a clearly labelled **HYPOTHETICAL / SYNTHETIC** elevation surface:

* a smooth, deterministic mathematical surface over the bounding box of the
  *verified* monitoring stations;
* a synthetic valley carved along each approximate river course so the channel
  is visually plausible.

The surface is a *visualisation scaffold* only.  Every artifact is tagged
``HYPOTHETICAL - NOT SURVEYED ELEVATION OR BATHYMETRY``.

Outputs
-------
* ``data/geojson/terrain_hypothetical.npz``   - grid + elevation array
* ``figures/3d/terrain_3d_hypothetical.png``  - 3-D surface + river overlay
* ``figures/3d/terrain_3d_river_<River>.png`` - per-river 3-D view

Usage
-----
    python code/terrain_3d_river_map.py
"""

from __future__ import annotations

import os
import sys
import json

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from mpl_toolkits.mplot3d import Axes3D  # noqa: E402
from shapely.geometry import LineString  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()

FIG_DIR = os.path.join(C.FIGURES_DIR, "3d")
os.makedirs(FIG_DIR, exist_ok=True)

LABEL = "HYPOTHETICAL - NOT SURVEYED ELEVATION OR BATHYMETRY"


def synthetic_dem(xs, ys, river_lines, sea_level=0.0):
    """Deterministic smooth surface with a carved valley along each river."""
    X, Y = np.meshgrid(xs, ys)
    # long-wavelength regional trend (harmless smooth hills)
    xspan = float(X.max() - X.min()) + 1e-9
    yspan = float(Y.max() - Y.min()) + 1e-9
    z = 120.0 * np.sin((X - X.min()) / xspan * 2 * np.pi * 1.5) + \
        90.0 * np.cos((Y - Y.min()) / yspan * 2 * np.pi * 2.0) + \
        50.0
    # carve a valley around each approximate river line
    for line in river_lines:
        coords = list(line.coords)
        arr = np.array(coords)
        for px, py in zip(X.ravel(), Y.ravel()):
            d = np.sqrt((arr[:, 0] - px) ** 2 + (arr[:, 1] - py) ** 2).min()
            i = np.where((X.ravel() == px) & (Y.ravel() == py))[0]
            if len(i):
                valley = 38.0 * np.exp(-(d / 0.06) ** 2)
                z.ravel()[i] -= valley
    z = np.clip(z, sea_level, None)
    return X, Y, z


def main():
    print("=" * 80)
    print("STAGE 9  -  3-D HYPOTHETICAL TERRAIN + RIVER")
    print("=" * 80)
    reg = pd.read_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"))
    reg = reg[reg["Latitude"].notna()]

    lon = reg["Longitude"].astype(float).values
    lat = reg["Latitude"].astype(float).values
    xs = np.linspace(lon.min() - 0.04, lon.max() + 0.04, 160)
    ys = np.linspace(lat.min() - 0.04, lat.max() + 0.04, 120)

    rivers = []
    for river, rg in reg.groupby("River"):
        pts = sorted([(float(a), float(b)) for a, b in zip(rg["Longitude"], rg["Latitude"])], key=lambda p: p[0])
        if len(pts) >= 2:
            rivers.append((river, LineString(pts)))

    X, Y, Z = synthetic_dem(xs, ys, [ln for _, ln in rivers])

    np.savez(os.path.join(C.DATA_DIR, "geojson", "terrain_hypothetical.npz"),
             xs=xs, ys=ys, X=X, Y=Y, Z=Z, label=LABEL)
    with open(os.path.join(C.DATA_DIR, "geojson", "terrain_hypothetical_provenance.json"), "w") as f:
        json.dump({"provenance": "synthetic", "label": LABEL,
                   "note": "No DEM or bathymetry available; surface is a mathematical visualisation scaffold.",
                   "bbox": [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]}, f, indent=1)

    # overall 3-D
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(X, Y, Z, cmap="terrain", rstride=3, cstride=3, alpha=0.85, linewidth=0)
    for river, line in rivers:
        cx, cy = line.xy
        ax.plot(cx, cy, np.interp(cx, X[0], Z[0]) * 0.0 + 8.0, color="#d62728", lw=2)
    ax.set_title(f"Central Luzon rivers - 3-D terrain (synthetic) | {LABEL}", fontsize=9)
    ax.set_xlabel("Longitude", fontsize=8)
    ax.set_ylabel("Latitude", fontsize=8)
    ax.set_zlabel("Elevation (hypothetical m)", fontsize=8)
    fig.colorbar(surf, ax=ax, shrink=0.6, label="elevation (hypothetical m)")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "terrain_3d_hypothetical.png"), dpi=120)
    plt.close(fig)

    # per-river 3-D views (top-down-ish)
    for river, line in rivers[:12]:
        bx = line.bounds
        x0 = int(np.searchsorted(xs, bx[0] - 0.01))
        x1 = int(np.searchsorted(xs, bx[2] + 0.01))
        y0 = int(np.searchsorted(ys, bx[1] - 0.01))
        y1 = int(np.searchsorted(ys, bx[3] + 0.01))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        fig = plt.figure(figsize=(6, 5))
        ax = fig.add_subplot(111, projection="3d")
        ax.plot_surface(X[y0:y1, x0:x1], Y[y0:y1, x0:x1], Z[y0:y1, x0:x1],
                        cmap="terrain", rstride=2, cstride=2, alpha=0.85)
        cx, cy = line.xy
        ax.plot(cx, cy, np.full_like(cx, 8.0), color="#d62728", lw=2.5)
        ax.set_title(f"{river} - 3-D (synthetic terrain) | {LABEL}", fontsize=8)
        ax.set_zlabel("elevation (hypothetical m)", fontsize=7)
        fig.tight_layout()
        fn = os.path.join(FIG_DIR, f"terrain_3d_river_{river.replace(' ', '_').replace('/', '_')}.png")
        fig.savefig(fn, dpi=120)
        plt.close(fig)

    print(f"saved hypothetical terrain grid + 3-D views to {FIG_DIR}")
    print("All elevation / bathymetry is explicitly HYPOTHETICAL.")
    print("DONE.")


if __name__ == "__main__":
    main()
