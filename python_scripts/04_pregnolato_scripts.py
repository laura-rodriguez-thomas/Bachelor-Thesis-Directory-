"""
Script 04 — Pregnolato flood speed reduction function
Implements the speed-depth relationship to translate flood depth
into a reduced vehicle speed. Uses the empirically derived
reduction factors from Pregnolato et al. (2017) 
"""

import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
FIGURES_FOLDER = PROJECT_ROOT / "08_maps"

def flood_reduced_speed(depth_mm, base_speed_kmh):
    
    if depth_mm == 0:
        return base_speed_kmh        # No flooding — full speed
    elif depth_mm == 100:
        return base_speed_kmh * 0.468   # Mild flooding
    elif depth_mm == 200:
        return base_speed_kmh * 0.142   # Moderate flooding
    elif depth_mm == 300:
        return 0.01                  # Severe flooding — road blocked
    else:
        raise ValueError(f"Unexpected depth: {depth_mm}. Must be 0, 100, 200, or 300.")
    

# ─────────────────────────────────────────────
# Test the function with sample roads
# ─────────────────────────────────────────────


print("Testing flood_reduced_speed() function:\n")
print(f"{'Road type':<15} {'Base':>6} {'0mm':>8} {'100mm':>8} {'200mm':>8} {'300mm':>8}")
print("-" * 60)

# Test cases — one fast road and one slow road
test_roads = [
    ("Motorway",     120),
    ("Primary",       60),
    ("Secondary",     40),
    ("Tertiary",      30),
    ("Residential",   20),
]

for name, base in test_roads:
    speeds = [flood_reduced_speed(d, base) for d in [0, 100, 200, 300]]
    print(f"{name:<15} {base:>6} {speeds[0]:>8.1f} {speeds[1]:>8.1f} {speeds[2]:>8.1f} {speeds[3]:>8.2f}")

# ─────────────────────────────────────────────
# The speed-depth curve
# ─────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(8, 5))

# Plot one line per road type
depths = [0, 100, 200, 300]
for name, base in test_roads:
    speeds = [flood_reduced_speed(d, base) for d in depths]
    ax.plot(depths, speeds, marker="o", label=f"{name} ({base} km/h base)")

# Threshold lines for the depth categories
ax.axvline(100, color="grey", linestyle=":", alpha=0.5)
ax.axvline(200, color="grey", linestyle=":", alpha=0.5)
ax.axvline(300, color="red",  linestyle=":", alpha=0.7)

# Axis labels and title
ax.set_xlabel("Flood depth (mm)")
ax.set_ylabel("Vehicle speed (km/h)")
ax.set_title("Speed reduction as a function of flood depth\n(Pregnolato et al., 2017)")
ax.legend(title="Road type")
ax.grid(True, alpha=0.3)

# Save as PDF (vector format, looks crisp in Word)
output_path = FIGURES_FOLDER / "pregnolato_speed_curve.pdf"
plt.savefig(output_path, bbox_inches="tight")

print(f"  Figure saved to: {output_path.name}")

print("Pregnolato function ready.")
