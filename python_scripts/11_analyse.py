"""
Script 11 — Statistical analysis and visualization
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats
from statsmodels.multivariate.manova import MANOVA
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RESULTS_CSV = PROJECT_ROOT / "07_tables_results" / "simulation_results.csv"
TABLES_DIR = PROJECT_ROOT / "07_tables_results"
FIGURES_DIR = PROJECT_ROOT / "08_maps"


STRATEGY_LABELS = {
    "distance": "Strategy 1: Distance (baseline)",
    "time":     "Strategy 2: Time (flood-aware)",
    "priority": "Strategy 3: Priority-weighted",
}
STRATEGY_ORDER = ["distance", "time", "priority"]


# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

# KPIs included in MANOVA (must have non-zero variance across the dataset).
MANOVA_KPIS = [
    "total_time_min",
    "total_distance_km",
    "people_reached_within_60min",
    "priority1_shelters_reached_within_60min",
    "avg_speed_kmh",
]

# Additional KPIs analyzed individually (Layer 2 ANOVA + Layer 3 t-tests)
PER_KPI_TESTS = MANOVA_KPIS + [
    "coverage_rate_pct",
    "shelters_reached_within_60min",
    "time_to_50pct_people_min",
]

# Pairwise comparisons for Layer 3
PAIRWISE_COMPARISONS = [
    ("distance", "time"),
    ("time",     "priority"),
    ("distance", "priority"),
]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def significance_marker(p):
    """Standard significance markers for p-values."""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def cohens_d(group1, group2):
    """
    Cohen's d effect size. Conventional thresholds (Cohen, 1988):
        |d| < 0.2 -> negligible
        0.2-0.5    -> small
        0.5-0.8    -> medium
        0.8+       -> large
    """
    n1, n2 = len(group1), len(group2)
    mean_diff = group1.mean() - group2.mean()
    pooled_std = np.sqrt(((n1 - 1) * group1.var(ddof=1) +
                          (n2 - 1) * group2.var(ddof=1)) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return mean_diff / pooled_std


def cohens_d_label(d):
    
    abs_d = abs(d)
    if abs_d < 0.2:
        return "negligible"
    if abs_d < 0.5:
        return "small"
    if abs_d < 0.8:
        return "medium"
    return "large"


# ─────────────────────────────────────────────
# Load data
# ─────────────────────────────────────────────

print("=" * 70)
print("STATISTICAL ANALYSIS")
print("=" * 70)
print("\nLoading simulation results...")
df = pd.read_csv(RESULTS_CSV)
print(f"  Loaded {len(df):,} rows")
print(f"  Hubs:       {sorted(df['supply_hub'].unique())}")
print(f"  Scenarios:  {sorted(df['scenario_id'].unique())}")
print(f"  Strategies: {sorted(df['strategy'].unique())}")
print(f"  Iterations per (hub x scenario x strategy): "
      f"{len(df) // (df['supply_hub'].nunique() * df['scenario_id'].nunique() * df['strategy'].nunique())}\n")


# ─────────────────────────────────────────────
# SUMMARY TABLES
# ─────────────────────────────────────────────

print("Building summary tables...")

# Final analytical KPI set (matches Script 09 output)
all_kpis = [
    "total_distance_km", "total_time_min", "avg_speed_kmh",
    "shelters_served", "shelters_unreachable",
    "total_people_served", "coverage_rate_pct",
    "time_to_50pct_people_min",
    "shelters_reached_within_60min", "priority1_shelters_reached_within_60min",
    "people_reached_within_60min", "priority1_people_reached_within_60min",
]

# Mean per scenario × strategy (averaged across hubs and iterations)
means = df.groupby(["scenario_id", "strategy"])[all_kpis].mean().round(2)
means.to_csv(TABLES_DIR / "summary_means.csv")

stds = df.groupby(["scenario_id", "strategy"])[all_kpis].std().round(2)
stds.to_csv(TABLES_DIR / "summary_stds.csv")

# 95% confidence intervals
ci_rows = []
for (scenario_id, strategy), group in df.groupby(["scenario_id", "strategy"]):
    row = {"scenario_id": scenario_id, "strategy": strategy, "n": len(group)}
    for kpi in all_kpis:
        m = group[kpi].mean()
        s = group[kpi].std()
        n = len(group)
        ci_half_width = 1.96 * s / np.sqrt(n)
        row[f"{kpi}_mean"]   = round(m, 2)
        row[f"{kpi}_ci_low"]  = round(m - ci_half_width, 2)
        row[f"{kpi}_ci_high"] = round(m + ci_half_width, 2)
    ci_rows.append(row)
ci_df = pd.DataFrame(ci_rows)
ci_df.to_csv(TABLES_DIR / "summary_with_ci.csv", index=False)

print(f"  Saved: summary_means.csv, summary_stds.csv, summary_with_ci.csv")


# ─────────────────────────────────────────────
# MANOVA per scenario
# ─────────────────────────────────────────────

print("\n" + "=" * 70)
print("MANOVA per scenario")
print("=" * 70)

manova_rows = []
for scenario_id in sorted(df["scenario_id"].unique()):
    scenario_df = df[df["scenario_id"] == scenario_id].copy()

    # MANOVA needs all KPIs to have variance > 0
    valid_kpis = [k for k in MANOVA_KPIS if scenario_df[k].std() > 0]

    if len(valid_kpis) < 2:
        manova_rows.append({
            "scenario_id":  scenario_id,
            "n_kpis_used":  len(valid_kpis),
            "wilks_lambda": np.nan,
            "f_statistic":  np.nan,
            "p_value":      np.nan,
            "significance": "skipped (insufficient variance)",
        })
        print(f"  S{scenario_id}: skipped (only {len(valid_kpis)} KPIs with variance)")
        continue

    formula = " + ".join(valid_kpis) + " ~ strategy"
    manova_result = MANOVA.from_formula(formula, data=scenario_df)
    test_stats = manova_result.mv_test().results["strategy"]["stat"]

    wilks_lambda = test_stats.loc["Wilks' lambda", "Value"]
    f_stat = test_stats.loc["Wilks' lambda", "F Value"]
    p_val = test_stats.loc["Wilks' lambda", "Pr > F"]

    manova_rows.append({
        "scenario_id":  scenario_id,
        "n_kpis_used":  len(valid_kpis),
        "wilks_lambda": round(wilks_lambda, 4),
        "f_statistic":  round(f_stat, 3),
        "p_value":      round(p_val, 6),
        "significance": significance_marker(p_val),
    })
    print(f"  S{scenario_id}: Wilks' lambda={wilks_lambda:.3f}, "
          f"F={f_stat:.2f}, p={p_val:.4g} {significance_marker(p_val)}")

manova_df = pd.DataFrame(manova_rows)
manova_df.to_csv(TABLES_DIR / "manova_results.csv", index=False)
print(f"  Saved -> manova_results.csv")


# ─────────────────────────────────────────────
# One-way ANOVA per KPI per scenario
# ─────────────────────────────────────────────

print("\n" + "=" * 70)
print("One-way ANOVA per KPI per scenario")
print("=" * 70)

anova_rows = []
for scenario_id in sorted(df["scenario_id"].unique()):
    for kpi in PER_KPI_TESTS:
        groups = [
            df[(df["scenario_id"] == scenario_id) & (df["strategy"] == s)][kpi].values
            for s in STRATEGY_ORDER
        ]
        if any(g.std() == 0 for g in groups):
            anova_rows.append({
                "scenario_id":  scenario_id,
                "kpi":          kpi,
                "f_statistic":  np.nan,
                "p_value":      np.nan,
                "significance": "skipped (no variance)",
            })
            continue
        f_stat, p_val = stats.f_oneway(*groups)
        anova_rows.append({
            "scenario_id":  scenario_id,
            "kpi":          kpi,
            "f_statistic":  round(f_stat, 3),
            "p_value":      round(p_val, 6),
            "significance": significance_marker(p_val),
        })

anova_df = pd.DataFrame(anova_rows)
anova_df.to_csv(TABLES_DIR / "anova_results.csv", index=False)
print(f"  Saved {len(anova_df)} ANOVA results -> anova_results.csv")


# ─────────────────────────────────────────────
# Bonferroni-corrected pairwise t-tests (post-hoc)
# ─────────────────────────────────────────────

print("\n" + "=" * 70)
print("LAYER 3: Bonferroni-corrected pairwise t-tests (post-hoc)")
print("=" * 70)

n_comparisons = len(PAIRWISE_COMPARISONS)
ttest_rows = []
effect_size_rows = []

for scenario_id in sorted(df["scenario_id"].unique()):
    for kpi in PER_KPI_TESTS:
        for s1, s2 in PAIRWISE_COMPARISONS:
            v1 = df[(df["scenario_id"] == scenario_id) & (df["strategy"] == s1)][kpi]
            v2 = df[(df["scenario_id"] == scenario_id) & (df["strategy"] == s2)][kpi]

            if v1.std() == 0 and v2.std() == 0:
                continue

            # Welch's t-test (unequal variances)
            t_stat, p_raw = stats.ttest_ind(v1, v2, equal_var=False)
            p_corrected = min(p_raw * n_comparisons, 1.0)

            d = cohens_d(v2, v1)

            ttest_rows.append({
                "scenario_id":  scenario_id,
                "kpi":          kpi,
                "strategy_1":   s1,
                "strategy_2":   s2,
                "mean_1":       round(v1.mean(), 2),
                "mean_2":       round(v2.mean(), 2),
                "diff":         round(v2.mean() - v1.mean(), 2),
                "t_statistic":  round(t_stat, 3),
                "p_raw":        round(p_raw, 6),
                "p_bonferroni": round(p_corrected, 6),
                "significance": significance_marker(p_corrected),
            })

            effect_size_rows.append({
                "scenario_id": scenario_id,
                "kpi":         kpi,
                "strategy_1":  s1,
                "strategy_2":  s2,
                "cohens_d":    round(d, 3),
                "magnitude":   cohens_d_label(d),
            })

ttest_df = pd.DataFrame(ttest_rows)
ttest_df.to_csv(TABLES_DIR / "ttests_bonferroni.csv", index=False)
print(f"  Saved {len(ttest_df)} pairwise t-tests -> ttests_bonferroni.csv")

effect_df = pd.DataFrame(effect_size_rows)
effect_df.to_csv(TABLES_DIR / "effect_sizes_cohens_d.csv", index=False)
print(f"  Saved {len(effect_df)} effect sizes -> effect_sizes_cohens_d.csv")


print("Script 11 complete.")
print(f"  Tables in: 07_tables_results/")
