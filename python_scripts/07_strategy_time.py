"""
Script 07 — Strategy 2: Time-based

"""

import networkx as nx
import math
import pickle
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GRAPH_FILE = PROJECT_ROOT / "09_models" / "routing_graph.pkl"

# Vehicle and kit parameters
KITS_PER_TRUCK = 320
PEOPLE_PER_KIT = 5
PEOPLE_PER_TRIP = KITS_PER_TRUCK * PEOPLE_PER_KIT


# ─────────────────────────────────────────────
# Helper: shortest path by flood-adjusted travel time
# ─────────────────────────────────────────────

def shortest_path_time(graph, start_node, end_node):
    """
    Find the shortest path between two nodes weighted by FLOOD-ADJUSTED
    TRAVEL TIME. Returns (path, total_distance_m, total_time_s).

    Unlike Strategy 1, this uses travel_time_flood_s as the routing cost,
    so the algorithm avoids slow flooded roads even if the geographic
    distance is longer.
    """
    try:
        path = nx.shortest_path(graph, start_node, end_node, weight="travel_time_flood_s")
        time_s = nx.shortest_path_length(graph, start_node, end_node, weight="travel_time_flood_s")

        # Calculate the actual distance covered along this fastest path
        distance_m = 0
        for i in range(len(path) - 1):
            edges_between = graph[path[i]][path[i + 1]]
            edge_data = edges_between[list(edges_between.keys())[0]]
            distance_m += edge_data["length_m"]

        return path, distance_m, time_s

    except nx.NetworkXNoPath:
        return None, None, None
    except nx.NodeNotFound:
        return None, None, None


# ─────────────────────────────────────────────
# Strategy 2: time-based routing with capacity + refill
# ─────────────────────────────────────────────

def route_by_time(graph, supply_node, supply_name, demand_nodes_to_visit):
    """
    Build a delivery route from a supply hub visiting all shelters,
    going to the fastest reachable unvisited shelter (by flood-adjusted
    travel time), respecting vehicle capacity and returning to refill
    when needed.
    """
    visit_order = []
    segments = []
    refill_count = 0
    total_distance_m = 0
    total_time_s = 0
    total_kits_delivered = 0

    current_node = supply_node
    kits_in_truck = KITS_PER_TRUCK

    if not demand_nodes_to_visit:
        return {
            "supply_hub": supply_name,
            "strategy": "time_based",
            "visit_order": [],
            "segments": [],
            "shelters_served": 0,
            "shelters_unreachable": 0,
            "unreachable_list": [],
            "total_distance_m": 0,
            "total_distance_km": 0,
            "total_time_s": 0,
            "total_time_min": 0,
            "total_kits_delivered": 0,
            "total_people_served": 0,
            "refill_count": 0,
        }

    remaining_demand = {
        shelter["shelter_id"]: math.ceil(shelter["capacity"] / PEOPLE_PER_KIT)
        for shelter in demand_nodes_to_visit
    }

    shelter_lookup = {s["shelter_id"]: s for s in demand_nodes_to_visit}
    unreachable = []

    while remaining_demand:
        # Pick the fastest-to-reach shelter with remaining demand
        best_shelter_id = None
        best_path = None
        best_time = float("inf")
        best_distance = None

        for sid in remaining_demand:
            target_node = shelter_lookup[sid]["nearest_node"]
            path, dist, time_s = shortest_path_time(graph, current_node, target_node)
            if path is not None and time_s < best_time:
                best_shelter_id = sid
                best_path = path
                best_time = time_s
                best_distance = dist

        if best_shelter_id is None:
            unreachable = [shelter_lookup[sid] for sid in remaining_demand]
            break

        shelter = shelter_lookup[best_shelter_id]
        kits_needed = remaining_demand[best_shelter_id]

        # Drive to the shelter
        segments.append({
            "type": "delivery_leg",
            "from": "hub" if current_node == supply_node else "shelter",
            "to_shelter": shelter["name"],
            "distance_m": best_distance,
            "travel_time_s": best_time,
            "path_length_segments": len(best_path) - 1,
        })
        total_distance_m += best_distance
        total_time_s += best_time
        current_node = shelter["nearest_node"]

        # Deliver kits
        kits_to_deliver = min(kits_needed, kits_in_truck)
        kits_in_truck -= kits_to_deliver
        remaining_demand[best_shelter_id] -= kits_to_deliver
        total_kits_delivered += kits_to_deliver

        segments.append({
            "type": "delivery",
            "shelter": shelter["name"],
            "kits_delivered": kits_to_deliver,
            "people_served": kits_to_deliver * PEOPLE_PER_KIT,
            "kits_remaining_at_shelter": remaining_demand[best_shelter_id],
            "kits_remaining_in_truck": kits_in_truck,
        })

        # Decide what happens next
        if remaining_demand[best_shelter_id] == 0:
            visit_order.append(shelter)
            del remaining_demand[best_shelter_id]

            if kits_in_truck == 0 and remaining_demand:
                # Refill trip
                path, dist, time_s = shortest_path_time(graph, current_node, supply_node)
                if path is None:
                    unreachable = [shelter_lookup[sid] for sid in remaining_demand]
                    break
                segments.append({"type": "refill_return", "distance_m": dist, "travel_time_s": time_s})
                total_distance_m += dist
                total_time_s += time_s
                current_node = supply_node
                kits_in_truck = KITS_PER_TRUCK
                refill_count += 1
        else:
            # Truck ran out — refill, come back to same shelter
            path, dist, time_s = shortest_path_time(graph, current_node, supply_node)
            if path is None:
                unreachable = [shelter_lookup[sid] for sid in remaining_demand]
                break
            segments.append({"type": "refill_return", "distance_m": dist, "travel_time_s": time_s})
            total_distance_m += dist
            total_time_s += time_s
            current_node = supply_node
            kits_in_truck = KITS_PER_TRUCK
            refill_count += 1

    return {
        "supply_hub": supply_name,
        "strategy": "time_based",
        "visit_order": visit_order,
        "segments": segments,
        "shelters_served": len(visit_order),
        "shelters_unreachable": len(unreachable),
        "unreachable_list": [s["name"] for s in unreachable],
        "total_distance_m": total_distance_m,
        "total_distance_km": total_distance_m / 1000,
        "total_time_s": total_time_s,
        "total_time_min": total_time_s / 60,
        "total_kits_delivered": total_kits_delivered,
        "total_people_served": total_kits_delivered * PEOPLE_PER_KIT,
        "refill_count": refill_count,
    }


# ─────────────────────────────────────────────
# Test with Scenario 4 iteration 0
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import importlib.util
    import geopandas as gpd

    spec = importlib.util.spec_from_file_location(
        "scenario_gen",
        Path(__file__).parent / "05_scenario_generator.py",
    )
    sg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sg)

    print("Loading base data...")
    with open(GRAPH_FILE, "rb") as f:
        bundle = pickle.load(f)
    base_graph = bundle["graph"]
    supply_nodes = bundle["supply_nodes"]
    demand_nodes = bundle["demand_nodes"]

    edges_flood = gpd.read_file(
        PROJECT_ROOT / "05_scenarios" / "edges_with_flood.gpkg"
    )

    print("Generating Scenario 4 iteration 0 flooded graph...")
    flooded = sg.generate_scenario(base_graph, edges_flood, scenario_id=4, iteration_seed=0)

    hub = supply_nodes.iloc[0]
    hub_node = hub["nearest_node"]

    shelters = [
        {
            "shelter_id": row["id"],
            "name": row["name"],
            "capacity": row["Capacity"],
            "priority": row["priority"],
            "nearest_node": row["nearest_node"],
        }
        for _, row in demand_nodes.iterrows()
    ]

    print(f"\nDispatching from: {hub['name']}")
    print(f"Visiting {len(shelters)} shelters")

    result = route_by_time(flooded, hub_node, hub["name"], shelters)

    print("\n" + "=" * 60)
    print("STRATEGY 2 — TIME-BASED ROUTING RESULT")
    print("=" * 60)
    print(f"Supply hub:           {result['supply_hub']}")
    print(f"Shelters served:      {result['shelters_served']} / {len(shelters)}")
    print(f"Shelters unreachable: {result['shelters_unreachable']}")
    print(f"Total distance:       {result['total_distance_km']:.2f} km")
    print(f"Total travel time:    {result['total_time_min']:.1f} min")
    print(f"Total kits delivered: {result['total_kits_delivered']}")
    print(f"Total people served:  {result['total_people_served']}")
    print(f"Refill trips to hub:  {result['refill_count']}")

    if result["unreachable_list"]:
        print(f"\nCould not reach: {', '.join(result['unreachable_list'])}")

    print(f"\nVisit order:")
    for i, shelter in enumerate(result["visit_order"], 1):
        print(f"  {i:>2}. {shelter['name']:<30} (capacity {shelter['capacity']:>5})")


    print("Strategy 2 test complete.")
  