"""
Script 06 — Strategy 1: Distance-based

"""

import networkx as nx
import math
import pickle
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GRAPH_FILE = PROJECT_ROOT / "09_models" / "routing_graph.pkl"

# ─────────────────────────────────────────────
# Vehicle and kit parameters (justified in spreadsheet)
# ─────────────────────────────────────────────
KITS_PER_TRUCK = 320              # max kits a truck can carry
PEOPLE_PER_KIT = 5                # 1 family kit = supplies for 5 people
PEOPLE_PER_TRIP = KITS_PER_TRUCK * PEOPLE_PER_KIT  # = 1600 people per fully loaded truck

# ─────────────────────────────────────────────
# Helper: shortest path by distance
# ─────────────────────────────────────────────

def shortest_path_distance(graph, start_node, end_node):
   
    try:
        path = nx.shortest_path(graph, start_node, end_node, weight="length_m")
        distance_m = nx.shortest_path_length(graph, start_node, end_node, weight="length_m")

        # Calculate the time using flood-adjusted speeds along the chosen path
        time_s = 0
        for i in range(len(path) - 1):
            edges_between = graph[path[i]][path[i + 1]]
            edge_data = edges_between[list(edges_between.keys())[0]]
            time_s += edge_data["travel_time_flood_s"]

        return path, distance_m, time_s

    except nx.NetworkXNoPath:
        return None, None, None
    except nx.NodeNotFound:
        return None, None, None
    
    # ─────────────────────────────────────────────
# Strategy 1: distance-based routing with vehicle capacity + refill
# ─────────────────────────────────────────────

def route_by_distance(graph, supply_node, supply_name, demand_nodes_to_visit):
    
    visit_order = []           # order shelters were fully served
    segments = []              # every leg of the trip (deliveries + refill returns)
    refill_count = 0           # how many times truck went back to refill
    total_distance_m = 0
    total_time_s = 0
    total_kits_delivered = 0

    # Truck starts full at the supply hub
    current_node = supply_node
    kits_in_truck = KITS_PER_TRUCK

    # Safety: if no shelters were passed in (all unreachable from hub),
    # return an empty result with all zeroed metrics. This prevents downstream
    # KPI logger from crashing on empty data.
    if not demand_nodes_to_visit:
        return {
            "supply_hub": supply_name,
            "strategy": "distance_based",
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


    # Each shelter has a "remaining demand" we track until fully served
    remaining_demand = {
        shelter["shelter_id"]: math.ceil(shelter["capacity"] / PEOPLE_PER_KIT)
        for shelter in demand_nodes_to_visit
    }

    # Build a quick lookup so we can find shelter info by id
    shelter_lookup = {s["shelter_id"]: s for s in demand_nodes_to_visit}

    # Track which shelters can't be reached at all
    unreachable = []

    # Main loop: keep delivering until all shelters are served or unreachable
    while remaining_demand:
        # Find the nearest reachable shelter that still needs supplies
        best_shelter_id = None
        best_path = None
        best_distance = float("inf")
        best_time = None

        for sid in remaining_demand:
            target_node = shelter_lookup[sid]["nearest_node"]
            path, dist, time_s = shortest_path_distance(graph, current_node, target_node)
            if path is not None and dist < best_distance:
                best_shelter_id = sid
                best_path = path
                best_distance = dist
                best_time = time_s

        # If nothing reachable, mark all remaining as unreachable and stop
        if best_shelter_id is None:
            unreachable = [shelter_lookup[sid] for sid in remaining_demand]
            break

        shelter = shelter_lookup[best_shelter_id]
        kits_needed = remaining_demand[best_shelter_id]

        # Drive to the shelter (whether full or partial delivery)
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

        # Deliver as many kits as possible 
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
            # Shelter fully served then remove from list, log to visit order
            visit_order.append(shelter)
            del remaining_demand[best_shelter_id]

            # If truck is empty and there are still shelters to serve, refill
            if kits_in_truck == 0 and remaining_demand:
                path, dist, time_s = shortest_path_distance(graph, current_node, supply_node)
                if path is None:
                    # Can't get back to hub then mark remaining as unreachable
                    unreachable = [shelter_lookup[sid] for sid in remaining_demand]
                    break
                segments.append({
                    "type": "refill_return",
                    "distance_m": dist,
                    "travel_time_s": time_s,
                })
                total_distance_m += dist
                total_time_s += time_s
                current_node = supply_node
                kits_in_truck = KITS_PER_TRUCK
                refill_count += 1
        else:
            # Shelter not fully served then it must be that the truck ran out
            # Return to hub, refill, then continue (truck will come back to this same shelter next loop)
            path, dist, time_s = shortest_path_distance(graph, current_node, supply_node)
            if path is None:
                unreachable = [shelter_lookup[sid] for sid in remaining_demand]
                break
            segments.append({
                "type": "refill_return",
                "distance_m": dist,
                "travel_time_s": time_s,
            })
            total_distance_m += dist
            total_time_s += time_s
            current_node = supply_node
            kits_in_truck = KITS_PER_TRUCK
            refill_count += 1

    # Result summary 
    return {
        "supply_hub": supply_name,
        "strategy": "distance_based",
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

    # Load Script 05 (scenario generator)
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

    # Pick the first supply hub
    hub = supply_nodes.iloc[0]
    hub_node = hub["nearest_node"]

    # Convert all 20 shelters to the format the routing function expects
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

    # Run Strategy 1
    print(f"\nDispatching from: {hub['name']}")
    print(f"Visiting {len(shelters)} shelters")
    print(f"Truck capacity: {KITS_PER_TRUCK} kits ({PEOPLE_PER_TRIP} people fully loaded)")

    result = route_by_distance(flooded, hub_node, hub["name"], shelters)

    #Print full delivery summary 
    print("\n" + "=" * 60)
    print("STRATEGY 1 — DISTANCE-BASED ROUTING RESULT")
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

    #  Print visit order with kits delivered 
    print(f"\nVisit order (in order of full completion):")
    for i, shelter in enumerate(result["visit_order"], 1):
        kits_needed = math.ceil(shelter["capacity"] / PEOPLE_PER_KIT)
        print(f"  {i:>2}. {shelter['name']:<30} (capacity {shelter['capacity']:>5} ppl, {kits_needed:>3} kits)")

    
    print(f"\nSegment log (first 15 of {len(result['segments'])} segments):")
    for i, seg in enumerate(result["segments"][:15], 1):
        if seg["type"] == "delivery_leg":
            print(f"  {i:>2}. DRIVE → {seg['to_shelter']:<28} {seg['distance_m']/1000:>6.2f} km, {seg['travel_time_s']/60:>5.1f} min")
        elif seg["type"] == "delivery":
            print(f"      DELIVER {seg['kits_delivered']:>3} kits at {seg['shelter']:<25} ({seg['people_served']} people, {seg['kits_remaining_in_truck']} kits left in truck)")
        elif seg["type"] == "refill_return":
            print(f"  {i:>2}. RETURN to hub for refill              {seg['distance_m']/1000:>6.2f} km, {seg['travel_time_s']/60:>5.1f} min")

    if len(result["segments"]) > 15:
        print(f"  ... ({len(result['segments']) - 15} more segments)")

    
    print("Strategy 1 test complete.")
    