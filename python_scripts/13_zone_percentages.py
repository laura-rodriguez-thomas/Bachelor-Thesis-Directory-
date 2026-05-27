"""
Script 13 — Compute realised network-wide flood percentages per scenario
For each of the six flood scenarios, computes what fraction of the
entire road network ends up flooded at each depth (100mm, 200mm, 300mm),

"""

import importlib.util
import geopandas as gpd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
EDGES_FLOOD_FILE = PROJECT_ROOT / "05_scenarios" / "edges_with_flood.gpkg"

# Load script 5
spec = importlib.util.spec_from_file_location(
    "scenario_gen",
    Path(__file__).parent / "05_scenario_generator.py"
)
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)
SCENARIOS = sg.SCENARIOS


# ─────────────────────────────────────────────
# Load the edges and count roads per zone
# ─────────────────────────────────────────────
edges = gpd.read_file(EDGES_FLOOD_FILE)
total_roads = len(edges)
print(f"  Total roads in network: {total_roads}")

zone_counts = edges["zone_name"].value_counts().to_dict()
print(f"\nRoads per zone:")
for zone in ["Very_High", "High", "Moderate", "None"]:
    count = zone_counts.get(zone, 0)
    pct = (count / total_roads) * 100
    print(f"  {zone:<12} {count:>6}  ({pct:>5.2f}% of network)")

# ─────────────────────────────────────────────
# Compute realised network-wide percentages per scenario
# ─────────────────────────────────────────────

print("\n" + "=" * 90)
print("REALISED NETWORK-WIDE FLOOD PERCENTAGES PER SCENARIO")
print("=" * 90)
print(f"\n{'Scenario':<10}{'100mm %':>14}{'200mm %':>14}{'300mm %':>14}{'Total %':>14}")
print("-" * 90)

for scenario_id, zone_data in SCENARIOS.items():
    count_100mm = 0
    count_200mm = 0
    count_300mm = 0

    for zone_name, depth_dict in zone_data.items():
        if zone_name == "demand":
            continue
        zone_total = zone_counts.get(zone_name, 0)
        count_100mm += zone_total * depth_dict.get(100, 0)
        count_200mm += zone_total * depth_dict.get(200, 0)
        count_300mm += zone_total * depth_dict.get(300, 0)

    pct_100 = (count_100mm / total_roads) * 100
    pct_200 = (count_200mm / total_roads) * 100
    pct_300 = (count_300mm / total_roads) * 100
    pct_total = pct_100 + pct_200 + pct_300

    print(f"S{scenario_id:<9}{pct_100:>13.2f}%{pct_200:>13.2f}%{pct_300:>13.2f}%{pct_total:>13.2f}%")

print("\n" + "=" * 90)
print("These are the network-wide percentages to report in Table 3.")
print("=" * 90)

# ─────────────────────────────────────────────
# Also show the per-zone percentages for transparency
# ─────────────────────────────────────────────

print("\nPer-zone breakdown:")
print(f"\n{'Scenario':<10}{'Zone':<12}{'100mm %':>10}{'200mm %':>10}{'300mm %':>10}{'Total %':>10}")
print("-" * 75)
for scenario_id, zone_data in SCENARIOS.items():
    for zone_name in ["Very_High", "High", "Moderate"]:
        if zone_name not in zone_data:
            continue
        depth_dict = zone_data[zone_name]
        pct_100 = depth_dict.get(100, 0) * 100
        pct_200 = depth_dict.get(200, 0) * 100
        pct_300 = depth_dict.get(300, 0) * 100
        pct_total = pct_100 + pct_200 + pct_300
        print(f"S{scenario_id:<9}{zone_name:<12}{pct_100:>9.0f}%{pct_200:>9.0f}%{pct_300:>9.0f}%{pct_total:>9.0f}%")
    print()