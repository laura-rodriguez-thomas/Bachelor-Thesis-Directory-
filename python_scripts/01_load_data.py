"""
Script 01: Load and verify all data files
"""

# libraries needed
import geopandas as gpd   # For reading GIS files and handling spatial data
import pandas as pd       # For tables and data manipulation
from pathlib import Path  # For handling file paths safely

# ─────────────────────────────────────────────
# Define paths to all input data files
# ─────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent

ROADS_FILE = PROJECT_ROOT / "02_processed_data" / "roads_final_reproj.gpkg"
NODES_FILE = PROJECT_ROOT / "04_demand_and_hubs" / "model_nodes.gpkg"
FLOOD_FILE = PROJECT_ROOT / "03_network_layers" / "flood_zones.gpkg"

print("Checking file paths...")
print(f"  Roads file:  {ROADS_FILE}")
print(f"  Nodes file:  {NODES_FILE}")
print(f"  Flood file:  {FLOOD_FILE}")

# ─────────────────────────────────────────────
# Load the road network
# ─────────────────────────────────────────────

print("\nLoading road network...")

roads = gpd.read_file(ROADS_FILE)

# Print basic info about the road network to confirm it loaded correctly
print(f"  Road segments loaded: {len(roads)}")
print(f"  Coordinate system:    {roads.crs}")
print(f"  Columns available:    {list(roads.columns)}")

# ─────────────────────────────────────────────
# Load the demand nodes (20 shelters)
# ─────────────────────────────────────────────

print("\nLoading demand nodes (shelters)...")

demand_nodes = gpd.read_file(NODES_FILE, layer="demand_nodes")

print(f"  Shelters loaded:     {len(demand_nodes)}")
print(f"  Coordinate system:   {demand_nodes.crs}")
print(f"  Columns available:   {list(demand_nodes.columns)}")
print(f"\n  First 3 shelters:")
print(demand_nodes[["id", "name", "Capacity", "priority"]].head(3))

# ─────────────────────────────────────────────
# Load the supply hubs (3 depots)
# ─────────────────────────────────────────────

print("\nLoading supply hubs (depots)...")

supply_nodes = gpd.read_file(NODES_FILE, layer="supply_nodes")

print(f"  Supply hubs loaded:  {len(supply_nodes)}")
print(f"  Coordinate system:   {supply_nodes.crs}")
print(f"  Columns available:   {list(supply_nodes.columns)}")
print(f"\n  All supply hubs:")
print(supply_nodes[["id", "name"]])

# ─────────────────────────────────────────────
# Load the flood zones (3 exposure levels)
# ─────────────────────────────────────────────

print("\nLoading flood zones...")

flood_zones = gpd.read_file(FLOOD_FILE)

print(f"  Flood polygons loaded: {len(flood_zones)}")
print(f"  Coordinate system:     {flood_zones.crs}")
print(f"  Columns available:     {list(flood_zones.columns)}")
print(f"\n  Zones by exposure level:")

print(flood_zones["zone_name"].value_counts())

# ─────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────

print("\n" + "=" * 50)
print("DATA LOADING SUMMARY")
print("=" * 50)
print(f"Road segments:  {len(roads):>6}")
print(f"Shelters:       {len(demand_nodes):>6}")
print(f"Supply hubs:    {len(supply_nodes):>6}")
print(f"Flood polygons: {len(flood_zones):>6}")
print("=" * 50)
print("All data loaded successfully")
