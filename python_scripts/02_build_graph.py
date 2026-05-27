"""
Script 02 — Build the routing graph using OSMnx

"""

import osmnx as ox
import geopandas as gpd
import networkx as nx
import pickle
from pathlib import Path
from shapely.geometry import Point

PROJECT_ROOT = Path(__file__).parent.parent
NODES_FILE = PROJECT_ROOT / "04_demand_and_hubs" / "model_nodes.gpkg"
ROADS_OUTPUT = PROJECT_ROOT / "02_processed_data" / "roads_osmnx.gpkg"
OUTPUT_GRAPH = PROJECT_ROOT / "09_models" / "routing_graph.pkl"
PLACE_NAME = "Distrito Nacional, Dominican Republic"

# ─────────────────────────────────────────────
# Download the road network from OpenStreetMap
# ─────────────────────────────────────────────

print(f"Downloading road network for {PLACE_NAME}...")

G = ox.graph_from_place(PLACE_NAME, network_type="drive")
print(f"  Nodes: {G.number_of_nodes()}")
print(f"  Edges: {G.number_of_edges()}")
G = ox.project_graph(G, to_crs="EPSG:32619")


# ─────────────────────────────────────────────
# Methodological choice: treat all roads as bidirectional
# ─────────────────────────────────────────────

G = ox.convert.to_undirected(G)
print(f"Graph after undirected conversion: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

# ─────────────────────────────────────────────
# Add base speed and travel time attributes to each edge
# ─────────────────────────────────────────────

SPEED_BY_TYPE = {
    "motorway":       120,
    "motorway_link":   40,
    "trunk":           80,
    "trunk_link":      40,
    "primary":         60,
    "primary_link":    40,
    "secondary":       40,
    "secondary_link":  30,
    "tertiary":        30,
    "tertiary_link":   20,
    "residential":     20,
    "service":         20,
    "living_street":   20,
    "unclassified":    20,
}

for u, v, key, data in G.edges(keys=True, data=True):
    highway = data.get("highway", "residential")
    if isinstance(highway, list):
        highway = highway[0]

    speed = SPEED_BY_TYPE.get(highway, 20)

    # Add the attributes to the edge
    data["speed_base"] = speed
    data["length_m"] = data.get("length", 0)
    # Travel time in minutes = (length in km / speed in km/h) × 60
    if speed > 0 and data["length_m"] > 0:
        data["time_base_min"] = (data["length_m"] / 1000 / speed) * 60
    else:
        data["time_base_min"] = 0



# ─────────────────────────────────────────────
# Save the road network as GeoPackage so you can view it in QGIS
# ─────────────────────────────────────────────

edges_gdf = ox.graph_to_gdfs(G, nodes=False, edges=True)
edges_gdf = edges_gdf.reset_index()
# Convert any list columns to strings so it can be saved
for col in edges_gdf.columns:
    if edges_gdf[col].apply(lambda x: isinstance(x, list)).any():
        edges_gdf[col] = edges_gdf[col].apply(lambda x: ",".join(map(str, x)) if isinstance(x, list) else x)
edges_gdf.to_file(ROADS_OUTPUT, driver="GPKG")
print(f"  Saved to: {ROADS_OUTPUT.name}")

# ─────────────────────────────────────────────
# Snap supply hubs and shelters to nearest road nodes
# ─────────────────────────────────────────────

supply_nodes = gpd.read_file(NODES_FILE, layer="supply_nodes")
demand_nodes = gpd.read_file(NODES_FILE, layer="demand_nodes")
# OSMnx's nearest_nodes function finds the closest graph node to each (x, y) point
supply_xs = supply_nodes.geometry.x.values
supply_ys = supply_nodes.geometry.y.values
demand_xs = demand_nodes.geometry.x.values
demand_ys = demand_nodes.geometry.y.values

supply_nodes["nearest_node"] = ox.distance.nearest_nodes(G, X=supply_xs, Y=supply_ys)
demand_nodes["nearest_node"] = ox.distance.nearest_nodes(G, X=demand_xs, Y=demand_ys)

print(f"  Snapped {len(supply_nodes)} supply hubs")
print(f"  Snapped {len(demand_nodes)} shelters")

# ─────────────────────────────────────────────
# Save the graph + snapped nodes to disk
# ─────────────────────────────────────────────


output = {
    "graph": G,
    "supply_nodes": supply_nodes,
    "demand_nodes": demand_nodes,
}

with open(OUTPUT_GRAPH, "wb") as f:
    pickle.dump(output, f)

print(f"  Saved to: {OUTPUT_GRAPH.name}")
print("Graph build complete.")