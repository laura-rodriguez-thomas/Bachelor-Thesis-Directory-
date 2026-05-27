"""
Script 10 — Master simulation loop
Runs the full simulation 
"""

import importlib.util
import pickle
import time
from datetime import datetime
import pandas as pd
import geopandas as gpd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GRAPH_FILE = PROJECT_ROOT / "09_models" / "routing_graph.pkl"
EDGES_FLOOD_FILE = PROJECT_ROOT / "05_scenarios" / "edges_with_flood.gpkg"
OUTPUT_CSV = PROJECT_ROOT / "07_tables_results" / "simulation_results.csv"

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

SUPPLY_HUB_INDICES = [0, 1, 2]              # 0 = Red Cross, 1 = Civil Defense, 2 = WFP HQ
SCENARIOS_TO_RUN = [1, 2, 3, 4, 5, 6]
ITERATIONS_PER_SCENARIO = 100
STRATEGIES_TO_RUN = ["distance", "time", "priority"]



SCENARIO_LABELS = {
    1: "S1: Dry baseline (0% network flooded)",
    2: "S2: Light rainfall (10.% network flooded, Very High zones start)",
    3: "S3: Heavy rainfall (20% network flooded)",
    4: "S4: Tropical storm (30% network flooded, 300mm impassability begins)",
    5: "S5: Cat 1-2 hurricane (40% network flooded)",
    6: "S6: Cat 3+ hurricane (50% network flooded)",
}

STRATEGY_LABELS = {
    "distance": "Strategy 1: Distance (baseline - ignores floods)",
    "time":     "Strategy 2: Time (flood-aware shortest time)",
    "priority": "Strategy 3: Priority-weighted (urgency-first)",
}


# ─────────────────────────────────────────────
# Helper to load each strategy module
# ─────────────────────────────────────────────

def load_module(filename, name):
    """Load a Python file by path so we can use modules with numeric prefixes."""
    spec = importlib.util.spec_from_file_location(
        name,
        Path(__file__).parent / filename,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────
# Main simulation loop
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("MASTER SIMULATION LOOP")
    print("=" * 70)

    # Load all required modules
    print("\nLoading scripts...")
    sg = load_module("05_scenario_generator.py", "scenario_gen")
    s1 = load_module("06_strategy_distance.py", "strategy1")
    s2 = load_module("07_strategy_time.py", "strategy2")
    s3 = load_module("08_strategy_priority.py", "strategy3")
    kpi = load_module("09_kpi_logger.py", "kpi_logger")

    # Load data
    print("Loading routing graph and shelter data...")
    with open(GRAPH_FILE, "rb") as f:
        bundle = pickle.load(f)
    base_graph = bundle["graph"]
    supply_nodes = bundle["supply_nodes"]
    demand_nodes = bundle["demand_nodes"]
    edges_flood = gpd.read_file(EDGES_FLOOD_FILE)

    # Show configuration
    print(f"\nConfigured supply hubs: "
          f"{[supply_nodes.iloc[i]['name'] for i in SUPPLY_HUB_INDICES]}")
    print(f"Scenarios:              {SCENARIOS_TO_RUN}")
    print(f"Iterations per scenario:{ITERATIONS_PER_SCENARIO}")
    print(f"Strategies:             {STRATEGIES_TO_RUN}")

    # Map strategy names to their functions
    strategy_functions = {
        "distance": s1.route_by_distance,
        "time":     s2.route_by_time,
        "priority": s3.route_by_priority,
    }

    all_results = []
    total_runs = (len(SUPPLY_HUB_INDICES) * len(SCENARIOS_TO_RUN)
                  * ITERATIONS_PER_SCENARIO * len(STRATEGIES_TO_RUN))
    run_count = 0
    start_time = time.time()

    print(f"\nTotal runs to execute: {total_runs}")
    print(f"Estimated time: ~{total_runs * 1.5 / 60:.0f} minutes\n")

    # ─── Loop hubs -> scenarios -> iterations -> strategies ───
    for hub_index in SUPPLY_HUB_INDICES:
        hub = supply_nodes.iloc[hub_index]
        hub_node = hub["nearest_node"]
        print(f"\n{'='*70}")
        print(f"  DISPATCHING FROM: {hub['name']}")
        print(f"{'='*70}")

        for scenario_id in SCENARIOS_TO_RUN:
            scenario = sg.SCENARIOS[scenario_id]
            demand_level = scenario["demand"]

            # Compute total fraction flooded per zone by summing across depths
        
            pct_moderate_zone_flooded  = sum(scenario["Moderate"].values())
            pct_high_zone_flooded      = sum(scenario["High"].values())
            pct_very_high_zone_flooded = sum(scenario["Very_High"].values())
            mean_occupancy_target = sg.occupancy_mean_for_scenario(scenario_id)

            # Pick activated shelters: low demand = Priority 1 only, high = all 20
            if demand_level == "low":
                activated = demand_nodes[demand_nodes["priority"] == 1]
            else:
                activated = demand_nodes

            shelters = [
                {
                    "shelter_id": row["id"],
                    "name": row["name"],
                    "capacity": row["Capacity"],
                    "priority": row["priority"],
                    "nearest_node": row["nearest_node"],
                }
                for _, row in activated.iterrows()
            ]

            print(f"\n--- {SCENARIO_LABELS[scenario_id]} | {len(shelters)} shelters ---")

            for iteration in range(ITERATIONS_PER_SCENARIO):
                # Generate the flooded graph (deterministic per iteration_seed)
                flooded = sg.generate_scenario(
                    base_graph, edges_flood,
                    scenario_id=scenario_id,
                    iteration_seed=iteration,
                )

                # Randomize shelter demand for this iteration
                shelters_this_iteration = sg.randomize_shelter_demand(
                    shelters, scenario_id=scenario_id, iteration_seed=iteration
                )

                # Compute realized values for transparency
                total_demand = sum(s["capacity"] for s in shelters_this_iteration)
                realized_occupancy = sum(
                    s["occupancy_fraction"] for s in shelters_this_iteration
                ) / len(shelters_this_iteration)

                # Pre-filter shelters by reachability
                reachable_shelters, structurally_unreachable = sg.find_reachable_shelters(
                    flooded, hub_node, shelters_this_iteration
                )

                for strategy_name in STRATEGIES_TO_RUN:
                    run_count += 1
                    strategy_fn = strategy_functions[strategy_name]

                    # Run strategy on REACHABLE shelters only
                    result = strategy_fn(flooded, hub_node, hub["name"], reachable_shelters)

                    # Capture strategy-level failures separately from structural ones
                    strategy_failed = result["shelters_unreachable"]
                    structural_failed = len(structurally_unreachable)

                    # Combine for KPI logger (which expects total unreachable)
                    result["shelters_unreachable"] = strategy_failed + structural_failed
                    result["unreachable_list"].extend(
                        [s["name"] for s in structurally_unreachable]
                    )

                    # Compute all KPIs
                    kpis = kpi.compute_all_kpis(result, demand_nodes, total_demand)

                    # Build the row (final trimmed schema)
                    row = {
                        # Identifiers
                        "run_timestamp":     datetime.now().isoformat(timespec="seconds"),
                        "supply_hub_index":  hub_index,
                        "supply_hub":        hub["name"],
                        "scenario_id":       scenario_id,
                        "scenario_label":    SCENARIO_LABELS[scenario_id],
                        "iteration":         iteration,
                        "strategy":          strategy_name,
                        "strategy_label":    STRATEGY_LABELS[strategy_name],

                        # Scenario parameters (transparency)
                        "demand_level":                  demand_level,
                        "pct_moderate_zone_flooded":     pct_moderate_zone_flooded,
                        "pct_high_zone_flooded":         pct_high_zone_flooded,
                        "pct_very_high_zone_flooded":    pct_very_high_zone_flooded,
                        "mean_occupancy_target":         round(mean_occupancy_target, 3),

                        # Realized values (what happened this iteration)
                        "shelters_activated":            len(shelters),
                        "total_demand_people":           total_demand,
                        "realized_mean_occupancy":       round(realized_occupancy, 3),

                        # KPIs from Script 09 
                        **kpis,
                    }
                    all_results.append(row)

                    # Progress indicator
                    elapsed = time.time() - start_time
                    avg_per_run = elapsed / run_count
                    remaining = (total_runs - run_count) * avg_per_run
                    print(f"  [{run_count:>4}/{total_runs}] "
                          f"Hub{hub_index} S{scenario_id} iter{iteration:>3} {strategy_name:<8} "
                          f"-> {kpis['total_time_min']:>6.1f} min, "
                          f"{kpis['shelters_served']}/{len(reachable_shelters)} served "
                          f"(ETA: {remaining/60:.1f} min)")

                # Save partial results after every iteration
                df = pd.DataFrame(all_results)
                df.to_csv(OUTPUT_CSV, index=False)

    # Final summary
    print(f"\n{'=' * 70}")
    print(f"All {len(all_results)} runs complete in {(time.time() - start_time)/60:.1f} minutes")
    print(f"Results saved to: {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"{'=' * 70}\n")

    df = pd.DataFrame(all_results)
    print("Quick summary by scenario x strategy (mean total_time_min):\n")
    summary = df.pivot_table(
        index="scenario_id",
        columns="strategy",
        values="total_time_min",
        aggfunc="mean",
    ).round(1)
    print(summary)

    print("\nDONE.")