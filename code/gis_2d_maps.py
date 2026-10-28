"""
gis_2d_maps.py
==============
Stage 8 of the pipeline.

Builds forecast-driven 2-D GIS maps of Central Luzon (Region III).

IMPORTANT - GEOMETRY PROVENANCE
------------------------------
Real hydrography shapefiles are NOT present in the repository and the sandbox
cannot reach a geospatial data host (data.humdata.org, USGS, etc.).  River
geometry is therefore approximated by connecting the *verified monitoring
station coordinates* of each river with a straight polyline and is explicitly
labelled ``APPROXIMATE - NOT SURVEYED GEOMETRY``.  It is a visual aid only and
must not be used for engineering or regulatory purposes.

Layers produced
--------------
* river lines     - approximate course per river (approximate geometry)
* station points  - verified coordinates (real)
* forecast points - horizon-1 forecast values per station/parameter (real)

Individual + combined chemical / physical / microbial maps are rendered.

Usage
-----
    python code/gis_2d_maps.py
"""

from __future__ import annotations

import os
import sys
import math
import json

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.colors import LogNorm, Normalize  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()

import geopandas as gpd  # noqa: E402

GEO_DIR = os.path.join(C.DATA_DIR, "geojson")
FIG_DIR = os.path.join(C.FIGURES_DIR, "2d")
os.makedirs(GEO_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

PROJ_CRS = "EPSG:4326"
DISCLAIMER = "APPROXIMATE river geometry (station-to-station) - NOT surveyed hydrography"
CHEM_PARAMS = ["DO", "BOD", "NH3", "NO3-N", "PO4-P", "Cl"]
PHYS_PARAMS = ["TSS", "Temp", "pH", "Color"]
MICRO_PARAMS = ["Fecal Coliform", "Total Coliform"]


def river_polylines(reg):
    """Approximate each river by connecting its verified stations in longitude order."""
    geoms, meta = [], []
    for river, rg in reg[reg["Latitude"].notna()].groupby("River"):
        pts = [(float(lon), float(lat)) for lat, lon in zip(rg["Latitude"], rg["Longitude"])]
        if len(pts) < 2:
            continue
        pts = sorted(pts, key=lambda p: p[0])          # longitude order (approximate downstream)
        geoms.append(LineString(pts))
        meta.append({"River": river, "N_Stations": len(pts), "Geometry_Type": "approximate"})
    if not geoms:
        return gpd.GeoDataFrame(), []
    gdf = gpd.GeoDataFrame(meta, geometry=geoms, crs=PROJ_CRS)
    return gdf, meta


def station_points(reg, forecasts):
    rows = []
    for _, r in reg[reg["Latitude"].notna()].iterrows():
        f = forecasts[(forecasts["River"] == r["River"]) & (forecasts["Station"] == r["Station_Canonical"])]
        n_fail = int((f["Classification"] == "Fail").sum()) if len(f) else 0
        n_f = len(f)
        rows.append({
            "River": r["River"], "Station": r["Station_Canonical"],
            "Latitude": float(r["Latitude"]), "Longitude": float(r["Longitude"]),
            "Coordinate_Confidence": r["Coordinate_Confidence"],
            "N_Forecast_Params": n_f, "N_Exceedances": n_fail,
            "Geometry_Type": "verified_station",
        })
    gdf = gpd.GeoDataFrame(rows, geometry=[Point(lo, la) for la, lo in
                                           zip([r["Latitude"] for r in rows], [r["Longitude"] for r in rows])],
                           crs=PROJ_CRS)
    return gdf


def forecast_points(forecasts, horizon=1):
    rows = []
    for _, f in forecasts[forecasts["Forecast_Horizon"] == horizon].iterrows():
        if pd.isna(f["Latitude"]) or pd.isna(f["Longitude"]):
            continue
        rows.append({
            "River": f["River"], "Station": f["Station"], "Parameter": f["Parameter"],
            "Latitude": float(f["Latitude"]), "Longitude": float(f["Longitude"]),
            "Forecast_Value": float(f["Forecast_Value"]), "Unit": f["Unit"],
            "Classification": f["Classification"], "Selected_Model": f["Selected_Model"],
            "Geometry_Type": "forecast_point",
        })
    return gpd.GeoDataFrame(rows, geometry=[Point(lo, la) for la, lo in
                                            zip([r["Latitude"] for r in rows], [r["Longitude"] for r in rows])],
                            crs=PROJ_CRS)


def param_value_bounds(forecasts, param, horizon=1):
    sub = forecasts[(forecasts["Parameter"] == param) & (forecasts["Forecast_Horizon"] == horizon)]
    sub = sub["Forecast_Value"].astype(float)
    return float(sub.min()), float(sub.max())


def render_map(ax, rivers_gdf, stations_gdf, fc_gdf, param, title, log_scale=False,
               legend_title=None):
    ax.set_title(title, fontsize=10)
    # rivers
    if len(rivers_gdf):
        rivers_gdf.plot(ax=ax, color="#7fb3d5", edgecolor="#2c3e50", lw=1.2, alpha=0.8, zorder=1)
    # stations
    if len(stations_gdf):
        sc = ax.scatter(stations_gdf.geometry.x, stations_gdf.geometry.y, c="#bdc3c7",
                        s=22, zorder=3, label="verified station")
    # forecast points
    if len(fc_gdf) and param:
        sub = fc_gdf[fc_gdf["Parameter"] == param]
        if len(sub):
            vals = sub["Forecast_Value"].astype(float)
            norm = LogNorm(vmin=max(vals.min(), 1e-6), vmax=vals.max()) if log_scale else \
                   Normalize(vmin=vals.min(), vmax=vals.max())
            sc = ax.scatter(sub.geometry.x, sub.geometry.y, c=vals, cmap="YlOrRd",
                            norm=norm, s=70, edgecolor="#1a1a1a", lw=0.5, zorder=4)
            ax.collections[-1].set_array(vals)
    ax.legend(handles=[Line2D([], [], color="#7fb3d5", lw=2, label="river (approximate)"),
                       Line2D([], [], marker="o", color="#bdc3c7", ls="", label="verified station")] +
                      ([Line2D([], [], marker="o", color="w", markerfacecolor="none", markeredgecolor="k", label=f"{param} forecast")] if param else []),
              fontsize=7, loc="lower left")
    ax.set_xlabel("Longitude (EPSG:4326)", fontsize=8)
    ax.set_ylabel("Latitude (EPSG:4326)", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.tick_params(labelsize=7)
    if log_scale and param:
        cbar = plt.colorbar(ax.collections[-1], ax=ax, fraction=0.04, pad=0.03)
        cbar.set_label(f"{param} forecast", fontsize=7)
    return sc


def main():
    print("=" * 80)
    print("STAGE 8  -  FORECAST-DRIVEN 2-D GIS MAPS")
    print("=" * 80)
    reg = pd.read_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"))
    forecasts = pd.read_csv(os.path.join(C.FORECAST_DIR, "future_four_quarter_forecasts.csv"))
    obs = pd.read_csv(os.path.join(C.PROCESSED_DIR, "observations_quarterly.csv"))

    rivers_gdf, river_meta = river_polylines(reg)
    stations_gdf = station_points(reg, forecasts)
    fc_gdf = forecast_points(forecasts)

    rivers_gdf.to_file(os.path.join(GEO_DIR, "rivers_approximate.geojson"), driver="GeoJSON")
    stations_gdf.to_file(os.path.join(GEO_DIR, "stations_verified.geojson"), driver="GeoJSON")
    fc_gdf.to_file(os.path.join(GEO_DIR, "forecast_points_h1.geojson"), driver="GeoJSON")
    print(f"river lines: {len(rivers_gdf)}  stations: {len(stations_gdf)}  forecast points: {len(fc_gdf)}")

    maps = []

    # individual chemical maps
    for param in CHEM_PARAMS:
        fig, ax = plt.subplots(figsize=(8, 6))
        render_map(ax, rivers_gdf, stations_gdf, fc_gdf, param,
                   f"{param} - 1-quarter forecast (class C) | {DISCLAIMER}",
                   log_scale=(param == "NH3"))
        fig.tight_layout()
        fn = os.path.join(FIG_DIR, f"2d_chemical_{param}.png")
        fig.savefig(fn, dpi=130); plt.close(fig)
        maps.append(fn)

    # individual physical maps
    for param in PHYS_PARAMS:
        fig, ax = plt.subplots(figsize=(8, 6))
        render_map(ax, rivers_gdf, stations_gdf, fc_gdf, param,
                   f"{param} - 1-quarter forecast (class C) | {DISCLAIMER}")
        fig.tight_layout()
        fn = os.path.join(FIG_DIR, f"2d_physical_{param}.png")
        fig.savefig(fn, dpi=130); plt.close(fig)
        maps.append(fn)

    # microbial
    for param in MICRO_PARAMS:
        fig, ax = plt.subplots(figsize=(8, 6))
        render_map(ax, rivers_gdf, stations_gdf, fc_gdf, param,
                   f"{param} - 1-quarter forecast (class C FC limit) | {DISCLAIMER}", log_scale=True)
        fig.tight_layout()
        fn = os.path.join(FIG_DIR, f"2d_microbial_{param.replace(' ', '_')}.png")
        fig.savefig(fn, dpi=130); plt.close(fig)
        maps.append(fn)

    # combined chemical map (mean of standardised failing-exceedance risk)
    fig, ax = plt.subplots(figsize=(8, 6))
    if len(rivers_gdf):
        rivers_gdf.plot(ax=ax, color="#7fb3d5", edgecolor="#2c3e50", lw=1.2, alpha=0.8, zorder=1)
    sub = stations_gdf[stations_gdf["N_Forecast_Params"] > 0].copy()
    if len(sub):
        norm = Normalize(vmin=sub["N_Exceedances"].min(), vmax=max(sub["N_Exceedances"].max(), 1))
        ax.scatter(sub.geometry.x, sub.geometry.y, c=sub["N_Exceedances"], cmap="RdYlGn_r",
                   norm=norm, s=60, edgecolor="#1a1a1a", lw=0.5, zorder=4)
        cbar = plt.colorbar(ax.collections[-1], ax=ax, fraction=0.04, pad=0.03)
        cbar.set_label("parameters exceeding Class C in 1-quarter forecast", fontsize=7)
    ax.legend(handles=[Line2D([], [], color="#7fb3d5", lw=2, label="river (approximate)"),
                       Line2D([], [], marker="o", color="w", markerfacecolor="w",
                              markeredgecolor="k", label="station (colour = #exceedances)")], fontsize=7, loc="lower left")
    ax.set_title(f"COMBINED chemical+physical - Class C exceedance count | {DISCLAIMER}", fontsize=10)
    ax.set_xlabel("Longitude (EPSG:4326)", fontsize=8); ax.set_ylabel("Latitude (EPSG:4326)", fontsize=8)
    ax.grid(True, alpha=0.3); ax.tick_params(labelsize=7)
    fig.tight_layout()
    fn = os.path.join(FIG_DIR, "2d_combined_all_parameters.png")
    fig.savefig(fn, dpi=130); plt.close(fig)
    maps.append(fn)

    # combined chemical-only
    fig, ax = plt.subplots(figsize=(8, 6))
    if len(rivers_gdf):
        rivers_gdf.plot(ax=ax, color="#7fb3d5", edgecolor="#2c3e50", lw=1.2, alpha=0.8, zorder=1)
    sub = stations_gdf[stations_gdf["N_Forecast_Params"] > 0].copy()
    if len(sub):
        ax.scatter(sub.geometry.x, sub.geometry.y, c=sub["N_Exceedances"], cmap="RdYlGn_r",
                   s=60, edgecolor="#1a1a1a", lw=0.5, zorder=4)
    ax.set_title(f"COMBINED chemical - Class C exceedance count | {DISCLAIMER}", fontsize=10)
    ax.set_xlabel("Longitude (EPSG:4326)", fontsize=8); ax.set_ylabel("Latitude (EPSG:4326)", fontsize=8)
    ax.grid(True, alpha=0.3); ax.tick_params(labelsize=7)
    fig.tight_layout()
    fn = os.path.join(FIG_DIR, "2d_combined_chemical.png")
    fig.savefig(fn, dpi=130); plt.close(fig)
    maps.append(fn)

    with open(os.path.join(C.RESULTS_DIR, "gis_map_index.json"), "w") as f:
        json.dump({"disclaimer": DISCLAIMER, "maps": maps, "geometry_provenance": "approximate"}, f, indent=1)
    print(f"\n{len(maps)} maps written to {FIG_DIR}")
    print("DONE.")


if __name__ == "__main__":
    main()
