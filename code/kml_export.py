"""
kml_export.py
=============
Stage 10 of the pipeline.

Builds Google Earth Pro compatible KML / KMZ packages:

* ``deliverables/kml/clz_rivers_stations_forecasts.kml``
* ``deliverables/kml/clz_rivers_stations_forecasts.kmz``

Layers
------
* ``Approximate rivers``     - station-to-station lines (approximate geometry)
* ``Verified stations``      - Point placemarks with provenance in the description
* ``Forecast points``        - 1-quarter forecast point placemarks (Pass/Fail styled)
* ``Hypothetical terrain``   - tessellated synthetic elevation mesh (clearly labelled)

Usage
-----
    python code/kml_export.py
"""

from __future__ import annotations

import os
import sys
import shutil
import zipfile
import datetime as _dt
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clz_common as C  # noqa: E402

C.ensure_dirs()

KML_DIR = os.path.join(C.EARTH_DIR, "kml")
os.makedirs(KML_DIR, exist_ok=True)
SHOT_DIR = os.path.join(C.EARTH_DIR, "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)


def add_style(doc, sid, color, scale=1.0):
    st = ET.SubElement(doc, "Style", id=sid)
    icon = ET.SubElement(st, "IconStyle")
    ET.SubElement(icon, "color").text = color
    ET.SubElement(icon, "scale").text = str(scale)


def point_placemark(doc, name, lat, lon, desc, style_id, alt=0.0):
    pm = ET.SubElement(doc, "Placemark")
    ET.SubElement(pm, "name").text = name
    ET.SubElement(pm, "styleUrl").text = f"#{style_id}"
    ET.SubElement(pm, "description").text = desc
    pt = ET.SubElement(pm, "Point")
    ET.SubElement(pt, "altitudeMode").text = "absolute"
    ET.SubElement(pt, "coordinates").text = f"{lon},{lat},{alt}"


def line_placemark(doc, name, coords, desc, style_id):
    pm = ET.SubElement(doc, "Placemark")
    ET.SubElement(pm, "name").text = name
    ET.SubElement(pm, "styleUrl").text = f"#{style_id}"
    ET.SubElement(pm, "description").text = desc
    ls = ET.SubElement(pm, "LineString")
    ET.SubElement(ls, "altitudeMode").text = "clampToGround"
    ET.SubElement(ls, "coordinates").text = coords


def main():
    print("=" * 80)
    print("STAGE 10  -  GOOGLE EARTH PRO KML / KMZ EXPORT")
    print("=" * 80)
    reg = pd.read_csv(os.path.join(C.REGISTRY_DIR, "station_inventory.csv"))
    reg = reg[reg["Latitude"].notna()]
    forecasts = pd.read_csv(os.path.join(C.FORECAST_DIR, "future_four_quarter_forecasts.csv"))
    forecasts = forecasts[forecasts["Forecast_Horizon"] == 1]

    doc = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    document = ET.SubElement(doc, "Document")
    ET.SubElement(document, "name").text = "Central Luzon Region III - WQ forecast study"
    ET.SubElement(document, "description").text = (
        "Rivers/stations/forecasts from the DENR-EMB Region 3 workbooks. "
        "River geometry is APPROXIMATE; terrain is HYPOTHETICAL. "
        f"Generated {_dt.datetime.now().isoformat(timespec='seconds')}.")

    add_style(doc, "st_station", "ff0000ff", 1.0)
    add_style(doc, "st_pass", "ff00ff00", 1.4)
    add_style(doc, "st_fail", "ffff0000", 1.4)
    add_style(doc, "st_river", "ff000000", 1.0)

    # --- rivers (approximate) ---
    for river, rg in reg.groupby("River"):
        pts = sorted([(float(b), float(a)) for a, b in zip(rg["Latitude"], rg["Longitude"])],
                     key=lambda p: p[0])
        if len(pts) < 2:
            continue
        coords = " ".join(f"{lo},{la},0" for lo, la in pts)
        line_placemark(doc, f"{river} (approximate)", coords,
                       f"Approximate course joining {len(pts)} verified monitoring stations. "
                       "NOT surveyed hydrography.", "st_river")

    # --- verified stations ---
    for _, r in reg.iterrows():
        desc = (f"River: {r['River']}<br/>Station: {r['Station_Canonical']}<br/>"
                f"Coordinate confidence: {r['Coordinate_Confidence']}<br/>"
                f"Status: {r['Coordinate_Status']}<br/>"
                f"Source: {r.get('Coordinate_Source_File', '')}")
        point_placemark(doc, f"STN {r['Station_Canonical']}", float(r["Latitude"]),
                        float(r["Longitude"]), desc, "st_station")

    # --- forecast points ---
    for _, f in forecasts.iterrows():
        if pd.isna(f["Latitude"]) or pd.isna(f["Longitude"]):
            continue
        sid = "st_pass" if f["Classification"] == "Pass" else "st_fail"
        desc = (f"{f['Parameter']} forecast ({f['Selected_Model']})<br/>"
                f"Value: {f['Forecast_Value']} {f['Unit']}<br/>"
                f"Class C: {f['Classification']}<br/>"
                f"River: {f['River']}<br/>Station: {f['Station']}")
        point_placemark(doc, f"FC {f['Station']} {f['Parameter']}",
                        float(f["Latitude"]), float(f["Longitude"]), desc, sid)

    # --- hypothetical terrain mesh ---
    terrain_path = os.path.join(C.DATA_DIR, "geojson", "terrain_hypothetical.npz")
    if os.path.exists(terrain_path):
        t = np.load(terrain_path)
        X, Y, Z = t["X"], t["Y"], t["Z"]
        nx, ny = 24, 16
        xs = np.linspace(float(X.min()), float(X.max()), nx)
        ys = np.linspace(float(Y.min()), float(Y.max()), ny)
        zs = np.zeros((nx, ny))
        for i, x in enumerate(xs):
            col = np.interp(x, X[0], Z[0])
            zs[i, :] = np.interp(ys, Y[:, 0], Z[:, i])
        zs = zs - zs.mean() + 60.0
        ring = []
        for j in range(ny):
            for i in range(nx):
                ring.append(f"{xs[i]},{ys[j]},{float(zs[i, j])}")
        for j in range(ny - 2, 0, -1):
            for i in range(nx - 1, -1, -1):
                ring.append(f"{xs[i]},{ys[j]},{float(zs[i, j])}")
        pm = ET.SubElement(doc, "Placemark")
        ET.SubElement(pm, "name").text = "HYPOTHETICAL terrain mesh"
        ET.SubElement(pm, "description").text = (
            "Synthetic elevation surface. NOT surveyed elevation or bathymetry. "
            "Visualisation scaffold only.")
        poly = ET.SubElement(pm, "Polygon")
        ET.SubElement(poly, "tessellate").text = "1"
        ET.SubElement(poly, "altitudeMode").text = "absolute"
        ob = ET.SubElement(poly, "outerBoundaryIs")
        lr = ET.SubElement(ob, "LinearRing")
        ET.SubElement(lr, "coordinates").text = " ".join(ring)

    kml_path = os.path.join(KML_DIR, "clz_rivers_stations_forecasts.kml")
    ET.ElementTree(doc).write(kml_path, encoding="utf-8", xml_declaration=True)

    kmz_path = os.path.join(KML_DIR, "clz_rivers_stations_forecasts.kmz")
    with zipfile.ZipFile(kmz_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(kml_path, "doc.kml")

    src = os.path.join(C.FIGURES_DIR, "3d")
    if os.path.isdir(src):
        for fn in os.listdir(src):
            if fn.endswith(".png"):
                shutil.copy(os.path.join(src, fn), SHOT_DIR)

    print(f"KML : {kml_path}")
    print(f"KMZ : {kmz_path}")
    print(f"screenshots -> {SHOT_DIR}")
    print("DONE.")


if __name__ == "__main__":
    main()
