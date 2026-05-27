"""
Script 03 — Intersect roads with flood zones
Figures out which roads sit inside flood zones and tags each one
with its max flood depth and exposure level. Then saves the result back
to a GeoPackage so we can open it in QGIS to visually verify, and
saves it as a CSV for later scripts to itload quickly.
"""

import geopandas as gpd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ROADS_FILE = PROJECT_ROOT / "02_processed_data" / "roads_osmnx.gpkg"
FLOOD_FILE = PROJECT_ROOT / "03_network_layers" / "flood_zones.gpkg"
OUTPUT_FILE = PROJECT_ROOT / "05_scenarios" / "edges_with_flood.gpkg"

# Load the roads and flood zones
roads = gpd.read_file(ROADS_FILE)
flood_zones = gpd.read_file(FLOOD_FILE)
print(f"  {len(roads)} roads, {len(flood_zones)} flood polygons")

# ─────────────────────────────────────────────
# Find which roads intersect which flood zones
# ─────────────────────────────────────────────

roads_flooded = gpd.sjoin(
    roads,
    flood_zones[["zone_name", "exposure_level", "max_depth_mm", "geometry"]],
    how="left",
    predicate="intersects"
)

roads_flooded = roads_flooded.sort_values("max_depth_mm", ascending=False)
roads_flooded = roads_flooded[~roads_flooded.index.duplicated(keep="first")]

# Roads that don't intersect any flood zone get NaN for max_depth. replace with 0
roads_flooded["max_depth_mm"] = roads_flooded["max_depth_mm"].fillna(0).astype(int)
roads_flooded["exposure_level"] = roads_flooded["exposure_level"].fillna(0).astype(int)
roads_flooded["zone_name"] = roads_flooded["zone_name"].fillna("None")

# Quick summary
print(roads_flooded["zone_name"].value_counts())

# ─────────────────────────────────────────────
# Save the classified roads
# ─────────────────────────────────────────────

print(f"\nSaving classified roads to {OUTPUT_FILE.name}...")
roads_flooded.to_file(OUTPUT_FILE, driver="GPKG")

print("Flood intersection complete.")
