"""
Script 09 — KPI logger
"""


# ─────────────────────────────────────────────
# Operational efficiency KPIs
# ─────────────────────────────────────────────

def kpi_total_distance_km(result):
    """Total distance driven across the entire route, including refill trips."""
    return result["total_distance_km"]


def kpi_total_time_min(result):
    """Total time including travel and refill drives."""
    return result["total_time_min"]


def kpi_avg_speed_kmh(result):
    """Average vehicle speed = total distance / total time. Lower means more flood disruption."""
    if result["total_time_min"] == 0:
        return 0
    return result["total_distance_km"] / (result["total_time_min"] / 60)


# ─────────────────────────────────────────────
# Coverage KPIs
# ─────────────────────────────────────────────

def kpi_shelters_served(result):
    """Number of shelters fully served (all kits delivered)."""
    return result["shelters_served"]


def kpi_shelters_unreachable(result):
    """Number of shelters that couldn't be reached due to flooding or hub disconnection."""
    return result["shelters_unreachable"]


def kpi_total_people_served(result):
    """Total people supplied = total kits x 5 (1 family kit serves 5 people, IFRC 2022)."""
    return result["total_people_served"]


def kpi_coverage_rate_pct(result):
    """
    Percentage of activated shelters that were fully served.
    coverage_rate = shelters_served / (shelters_served + shelters_unreachable) x 100
    """
    total_activated = result["shelters_served"] + result["shelters_unreachable"]
    if total_activated == 0:
        return 0
    return (result["shelters_served"] / total_activated) * 100


# ─────────────────────────────────────────────
# Speed-of-response (equity) KPIs
# ─────────────────────────────────────────────

def _build_arrival_timeline(result):
    
    timeline = []
    elapsed_s = 0
    people_served_so_far = 0
    seen_shelters = set()
    shelter_to_entry = {}

    for seg in result["segments"]:
        if seg["type"] == "delivery_leg":
            elapsed_s += seg["travel_time_s"]
            if seg["to_shelter"] not in seen_shelters:
                seen_shelters.add(seg["to_shelter"])
                entry = {
                    "shelter_name": seg["to_shelter"],
                    "arrival_time_min": elapsed_s / 60,
                    "people_served_so_far": people_served_so_far,
                }
                timeline.append(entry)
                shelter_to_entry[seg["to_shelter"]] = entry
        elif seg["type"] == "delivery":
            people_served_so_far += seg["people_served"]
            if seg["shelter"] in shelter_to_entry:
                shelter_to_entry[seg["shelter"]]["people_served_so_far"] = people_served_so_far
        elif seg["type"] == "refill_return":
            elapsed_s += seg["travel_time_s"]

    return timeline


def kpi_time_to_50pct_people_min(result, total_demand_people):
    """When was half the total demand reached?"""
    timeline = _build_arrival_timeline(result)
    half = total_demand_people / 2
    for entry in timeline:
        if entry["people_served_so_far"] >= half:
            return entry["arrival_time_min"]
    return result["total_time_min"]


def kpi_shelters_reached_within_60min(result):
    """Count of shelters first reached within 60 minutes."""
    timeline = _build_arrival_timeline(result)
    return sum(1 for entry in timeline if entry["arrival_time_min"] <= 60)


def kpi_priority1_shelters_reached_within_60min(result, demand_nodes):
    """Count of Priority 1 (Very_High zone) shelters reached within 60 minutes."""
    priority_lookup = {row["name"]: row["priority"] for _, row in demand_nodes.iterrows()}
    timeline = _build_arrival_timeline(result)
    count = 0
    for entry in timeline:
        if entry["arrival_time_min"] <= 60:
            if priority_lookup.get(entry["shelter_name"]) == 1:
                count += 1
    return count


def kpi_people_reached_within_60min(result):
    """
    Total people supplied within the first 60 minutes of operation.
    Returns the maximum people_served_so_far across timeline entries
    whose arrival_time_min is <= 60.
    """
    timeline = _build_arrival_timeline(result)
    if not timeline:
        return 0
    eligible = [entry["people_served_so_far"]
                for entry in timeline if entry["arrival_time_min"] <= 60]
    return max(eligible) if eligible else 0


def kpi_priority1_people_reached_within_60min(result, demand_nodes):
    """People supplied at Priority 1 shelters within the first 60 minutes."""
    priority_lookup = {row["name"]: row["priority"] for _, row in demand_nodes.iterrows()}

    elapsed_s = 0
    p1_people = 0
    for seg in result["segments"]:
        if seg["type"] == "delivery_leg":
            elapsed_s += seg["travel_time_s"]
            if elapsed_s / 60 > 60:
                break
        elif seg["type"] == "delivery":
            if elapsed_s / 60 <= 60:
                if priority_lookup.get(seg["shelter"]) == 1:
                    p1_people += seg["people_served"]
        elif seg["type"] == "refill_return":
            elapsed_s += seg["travel_time_s"]
    return p1_people


# ─────────────────────────────────────────────
# Master function
# ─────────────────────────────────────────────

def compute_all_kpis(result, demand_nodes, total_demand_people):
    """
    Compute every KPI defined in this script and return a flat dictionary
    ready to be written to a CSV row.
    """
    return {
        # Operational efficiency
        "total_distance_km":              kpi_total_distance_km(result),
        "total_time_min":                 kpi_total_time_min(result),
        "avg_speed_kmh":                  kpi_avg_speed_kmh(result),
        # Coverage
        "shelters_served":                kpi_shelters_served(result),
        "shelters_unreachable":           kpi_shelters_unreachable(result),
        "total_people_served":            kpi_total_people_served(result),
        "coverage_rate_pct":              kpi_coverage_rate_pct(result),
        # Speed of response (equity)
        "time_to_50pct_people_min":       kpi_time_to_50pct_people_min(result, total_demand_people),
        "shelters_reached_within_60min":  kpi_shelters_reached_within_60min(result),
        "priority1_shelters_reached_within_60min": kpi_priority1_shelters_reached_within_60min(result, demand_nodes),
        "people_reached_within_60min":    kpi_people_reached_within_60min(result),
        "priority1_people_reached_within_60min": kpi_priority1_people_reached_within_60min(result, demand_nodes),
    }


# ─────────────────────────────────────────────
# Test with a sample run from each strategy
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import importlib.util
    import pickle
    import geopandas as gpd
    from pathlib import Path

    PROJECT_ROOT = Path(__file__).parent.parent
    GRAPH_FILE = PROJECT_ROOT / "09_models" / "routing_graph.pkl"

    def load_module(filename, name):
        spec = importlib.util.spec_from_file_location(
            name,
            Path(__file__).parent / filename,
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    sg = load_module("05_scenario_generator.py", "scenario_gen")
    s1 = load_module("06_strategy_distance.py", "strategy1")
    s2 = load_module("07_strategy_time.py", "strategy2")
    s3 = load_module("08_strategy_priority.py", "strategy3")

    print("Loading data...")
    with open(GRAPH_FILE, "rb") as f:
        bundle = pickle.load(f)
    base_graph = bundle["graph"]
    supply_nodes = bundle["supply_nodes"]
    demand_nodes = bundle["demand_nodes"]
    edges_flood = gpd.read_file(PROJECT_ROOT / "05_scenarios" / "edges_with_flood.gpkg")

    print("Generating Scenario 4 iteration 0...")
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
    total_demand = sum(s["capacity"] for s in shelters)

    print(f"\nRunning all 3 strategies (total demand = {total_demand} people)\n")
    print(f"{'KPI':<45} {'S1 Distance':>12} {'S2 Time':>12} {'S3 Priority':>12}")
    print("-" * 85)

    results = {
        "S1": s1.route_by_distance(flooded, hub_node, hub["name"], shelters),
        "S2": s2.route_by_time(flooded, hub_node, hub["name"], shelters),
        "S3": s3.route_by_priority(flooded, hub_node, hub["name"], shelters),
    }

    kpi_dicts = {
        name: compute_all_kpis(res, demand_nodes, total_demand)
        for name, res in results.items()
    }

    for kpi_name in kpi_dicts["S1"].keys():
        s1_val = kpi_dicts["S1"][kpi_name]
        s2_val = kpi_dicts["S2"][kpi_name]
        s3_val = kpi_dicts["S3"][kpi_name]

        def fmt(v):
            if isinstance(v, str):
                return v[:12] if len(v) > 0 else "-"
            elif isinstance(v, float):
                return f"{v:.2f}"
            else:
                return str(v)

        print(f"{kpi_name:<45} {fmt(s1_val):>12} {fmt(s2_val):>12} {fmt(s3_val):>12}")

 
    print("KPI logger working.")
  