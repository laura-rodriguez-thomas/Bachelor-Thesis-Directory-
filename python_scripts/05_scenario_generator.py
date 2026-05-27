"""
Script 05 — Scenario generator
Builds flooded versions of the road network according to the scenario
matrix.

"""

import geopandas as gpd
import numpy as np
import pickle
from pathlib import Path
from copy import deepcopy

PROJECT_ROOT = Path(__file__).parent.parent
GRAPH_FILE = PROJECT_ROOT / "09_models" / "routing_graph.pkl"
FLOOD_EDGES = PROJECT_ROOT / "05_scenarios" / "edges_with_flood.gpkg"

#  
# Pregnolato function from Script 04
import importlib.util
spec = importlib.util.spec_from_file_location(
    "pregnolato",
    Path(__file__).parent / "04_pregnolato_scripts.py"
)
pregnolato_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pregnolato_module)
flood_reduced_speed = pregnolato_module.flood_reduced_speed

# ─────────────────────────────────────────────
# Scenario matrix
# ─────────────────────────────────────────────

SCENARIOS = {
    1: {
        "Very_High": {100: 0.00, 200: 0.00, 300: 0.00},
        "High":      {100: 0.00, 200: 0.00},
        "Moderate":  {100: 0.00},
        "demand": "low",
    },
    2: {
        "Very_High": {100: 0.20, 200: 0.00, 300: 0.00},
        "High":      {100: 0.15, 200: 0.00},
        "Moderate":  {100: 0.00},
        "demand": "low",
    },
    3: {
        "Very_High": {100: 0.10, 200: 0.20, 300: 0.00},
        "High":      {100: 0.10, 200: 0.20},
        "Moderate":  {100: 0.05},
        "demand": "low",
    },
    4: {
        "Very_High": {100: 0.15, 200: 0.25, 300: 0.10},
        "High":      {100: 0.15, 200: 0.30},
        "Moderate":  {100: 0.10},
        "demand": "high",
    },
    5: {
        "Very_High": {100: 0.15, 200: 0.30, 300: 0.20},
        "High":      {100: 0.15, 200: 0.40},
        "Moderate":  {100: 0.20},
        "demand": "high",
    },
    6: {
        "Very_High": {100: 0.10, 200: 0.35, 300: 0.30},
        "High":      {100: 0.15, 200: 0.50},
        "Moderate":  {100: 0.30},
        "demand": "high",
    },
}

# ─────────────────────────────────────────────
# Flooded graph for one scenario + iteration
# ─────────────────────────────────────────────

def generate_scenario(graph, edges_with_flood, scenario_id, iteration_seed):

    # Get the scenario configuration
    scenario = SCENARIOS[scenario_id]

    # Seed the random number generator for this iteration
    rng = np.random.default_rng(iteration_seed)

    # Copy the graph so the original is untouched
    flooded_graph = deepcopy(graph)

    # Loop over each zone in the scenario
    for zone_name, depth_dict in scenario.items():
        # Skip the "demand" key — it's not a zone
        if zone_name == "demand":
            continue

        # Find all roads in this zone
        zone_roads = edges_with_flood[edges_with_flood["zone_name"] == zone_name]
        if len(zone_roads) == 0:
            continue

        # Pool of indices still available to flood (we remove from this pool
        # as we sample for each depth, to prevent double-flooding)
        available_indices = list(range(len(zone_roads)))

        # Process depths from deepest to shallowest within a zone, so the
        # deeper depths get first pick of segments. 
        depths_sorted = sorted(depth_dict.keys(), reverse=True)

        for depth in depths_sorted:
            fraction = depth_dict[depth]
            if fraction == 0 or len(available_indices) == 0:
                continue

            # How many segments to flood at this depth
            n_to_flood = int(round(len(zone_roads) * fraction))
            n_to_flood = min(n_to_flood, len(available_indices))
            if n_to_flood == 0:
                continue

            # Pick segments randomly from the available pool
            chosen_pool_indices = rng.choice(
                len(available_indices), size=n_to_flood, replace=False
            )
            chosen_road_indices = [available_indices[i] for i in chosen_pool_indices]
            flooded_roads = zone_roads.iloc[chosen_road_indices]

            # Remove them from the pool so they aren't re-selected
            chosen_set = set(chosen_road_indices)
            available_indices = [i for i in available_indices if i not in chosen_set]

            # Apply the flood depth to each chosen road
            for _, road in flooded_roads.iterrows():
                u = road["u"]
                v = road["v"]

                # 300mm = impassable, remove from graph entirely
                if depth >= 300:
                    if flooded_graph.has_edge(u, v):
                        flooded_graph.remove_edge(u, v)
                    if flooded_graph.has_edge(v, u):
                        flooded_graph.remove_edge(v, u)
                    continue

                # Otherwise slow down both directions
                if flooded_graph.has_edge(u, v):
                    for key in flooded_graph[u][v]:
                        edge_data = flooded_graph[u][v][key]
                        base_speed = edge_data["speed_base"]
                        edge_data["flood_depth_mm"] = depth
                        edge_data["speed_flood"] = flood_reduced_speed(depth, base_speed)
                        speed_ms = edge_data["speed_flood"] / 3.6
                        length_m = edge_data["length_m"]
                        edge_data["travel_time_flood_s"] = length_m / speed_ms

                if flooded_graph.has_edge(v, u):
                    for key in flooded_graph[v][u]:
                        edge_data = flooded_graph[v][u][key]
                        base_speed = edge_data["speed_base"]
                        edge_data["flood_depth_mm"] = depth
                        edge_data["speed_flood"] = flood_reduced_speed(depth, base_speed)
                        speed_ms = edge_data["speed_flood"] / 3.6
                        length_m = edge_data["length_m"]
                        edge_data["travel_time_flood_s"] = length_m / speed_ms

    # All non-flooded roads keep their base speed
    for u, v, key, data in flooded_graph.edges(keys=True, data=True):
        if "flood_depth_mm" not in data:
            data["flood_depth_mm"] = 0
            data["speed_flood"] = data["speed_base"]
            data["travel_time_flood_s"] = (data["length_m"] / (data["speed_base"] / 3.6))

    return flooded_graph


# ─────────────────────────────────────────────
# Reachability pre-filter (UNCHANGED from previous version)
# ─────────────────────────────────────────────

import networkx as nx


def find_reachable_shelters(flooded_graph, supply_node, demand_nodes_to_visit):
    """
    Partition the demand_nodes_to_visit list into reachable and unreachable
    based on connected-component membership relative to the supply hub.
    """
    undirected = flooded_graph.to_undirected()

    hub_component = None
    for component in nx.connected_components(undirected):
        if supply_node in component:
            hub_component = component
            break

    if hub_component is None:
        return [], list(demand_nodes_to_visit)

    reachable = []
    unreachable = []
    for shelter in demand_nodes_to_visit:
        if shelter["nearest_node"] in hub_component:
            reachable.append(shelter)
        else:
            unreachable.append(shelter)

    return reachable, unreachable


# ─────────────────────────────────────────────
# Variable shelter demand per iteration 
# ─────────────────────────────────────────────

DEMAND_OCCUPANCY_STD = 0.10


def occupancy_mean_for_scenario(scenario_id):
    """Linear scaling: 25% at S1 → 100% at S6."""
    return 0.25 + 0.15 * (scenario_id - 1)


def randomize_shelter_demand(shelters, scenario_id, iteration_seed):
    """
    Generate a per-iteration demand realization. Each shelter's effective
    demand = capacity × occupancy_fraction, drawn from Normal(μ, 0.10),
    clipped to [0, 1].
    """
    import numpy as np
    rng = np.random.default_rng(seed=iteration_seed * 1000 + scenario_id)

    mean = occupancy_mean_for_scenario(scenario_id)
    std = DEMAND_OCCUPANCY_STD

    randomized = []
    for s in shelters:
        fraction = rng.normal(mean, std)
        fraction = max(0.0, min(1.0, fraction))
        new_capacity = int(round(s["capacity"] * fraction))
        new_shelter = dict(s)
        new_shelter["capacity"] = new_capacity
        new_shelter["original_capacity"] = s["capacity"]
        new_shelter["occupancy_fraction"] = round(fraction, 3)
        randomized.append(new_shelter)

    return randomized


# ─────────────────────────────────────────────
# Test the generator
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Loading base data...")
    with open(GRAPH_FILE, "rb") as f:
        bundle = pickle.load(f)
    base_graph = bundle["graph"]
    edges_flood = gpd.read_file(FLOOD_EDGES)

    print(f"  {base_graph.number_of_edges()} edges in graph")
    print(f"  {len(edges_flood)} edges with flood data\n")

    # Test each scenario, with iteration 0
    for scenario_id in range(1, 7):
        print(f"Generating Scenario {scenario_id}, iteration 0...")
        flooded = generate_scenario(base_graph, edges_flood, scenario_id=scenario_id, iteration_seed=0)

        depth_counts = {0: 0, 100: 0, 200: 0, 300: 0}
        for u, v, data in flooded.edges(data=True):
            depth_counts[data["flood_depth_mm"]] += 1

        total_passable = sum(depth_counts.values())
        # 300mm edges have been removed from the graph, so count those separately
        n_removed = base_graph.number_of_edges() - flooded.number_of_edges()

        print(f"  Depth distribution in flooded graph:")
        print(f"    0 mm (dry):      {depth_counts[0]:>5} edges")
        print(f"    100 mm:          {depth_counts[100]:>5} edges")
        print(f"    200 mm:          {depth_counts[200]:>5} edges")
        print(f"    300 mm (removed):{n_removed:>5} edges")
        n_flooded = depth_counts[100] + depth_counts[200] + n_removed
        pct_flooded = 100 * n_flooded / base_graph.number_of_edges()
        print(f"    Total flooded: {n_flooded} ({pct_flooded:.1f}% of network)\n")

    
    print("Scenario generator working.")
    