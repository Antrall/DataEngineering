"""
Графики для отчёта: профилирование (время и память) и рост числа комбинаций навыков.
Запуск (из корня HW3): python src/make_charts.py
"""
import csv
import json
import statistics
from pathlib import Path

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt


PROFILE_PATH = Path("results/profile_results.csv")
SUMMARY_PATH = Path("results/mapreduce/summary.json")
OUTPUT_DIR = Path("report/images")

SHORT_METHOD_NAMES = {
    "MapReduce v1 (before optimization)": "v1",
    "MapReduce (optimized, 4 processes)": "optimized,\n4 proc.",
    "MapReduce (optimized, 1 process)": "optimized,\n1 proc.",
    "DuckDB SQL": "DuckDB",
}

BAR_COLOR = "#4c78a8"
LIGHT_BAR_COLOR = "#9ecae9"
MEMORY_BAR_COLOR = "#f58518"


def add_value_labels(axis, values):
    for position, value in enumerate(values):
        label = f"{value:.0f}" if value > 50 else f"{value:.1f}"
        axis.text(position, value, label, ha="center", va="bottom", fontsize=9)


def draw_profile_chart():
    with open(PROFILE_PATH, encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    methods = list(dict.fromkeys(row["method"] for row in rows))
    mean_times = [
        statistics.mean(float(row["time_s"]) for row in rows if row["method"] == method)
        for method in methods
    ]
    mean_memories = [
        statistics.mean(float(row["peak_mem_mib"]) for row in rows if row["method"] == method)
        for method in methods
    ]
    labels = [SHORT_METHOD_NAMES[method] for method in methods]

    figure, (time_axis, memory_axis) = plt.subplots(1, 2, figsize=(9, 3.6))
    time_axis.bar(labels, mean_times, color=BAR_COLOR)
    time_axis.set_title("Time, s (mean of 3 runs)")
    memory_axis.bar(labels, mean_memories, color=MEMORY_BAR_COLOR)
    memory_axis.set_title("Peak memory, MiB (mean of 3 runs)")

    for axis, values in ((time_axis, mean_times), (memory_axis, mean_memories)):
        add_value_labels(axis, values)
        axis.tick_params(axis="x", labelsize=8)

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "08_profile.png", dpi=130)
    plt.close(figure)


def draw_growth_chart():
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    stack_sizes = ["1", "2", "3"]
    unique_counts = [summary["unique"][size] for size in stack_sizes]
    emitted_counts = [summary["emitted"][size] for size in stack_sizes]

    figure, axis = plt.subplots(figsize=(6, 3.4))
    positions = range(len(stack_sizes))
    axis.bar([p - 0.2 for p in positions], emitted_counts, 0.4, label="occurrences (sum of frequencies)", color=LIGHT_BAR_COLOR)
    axis.bar([p + 0.2 for p in positions], unique_counts, 0.4, label="unique keys", color=BAR_COLOR)
    axis.set_yscale("log")
    axis.set_xticks(list(positions))
    axis.set_xticklabels(["single skills", "pairs", "triples"])
    axis.legend(fontsize=8)
    axis.set_title("Growth of the number of keys (log scale)")

    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "09_growth.png", dpi=130)
    plt.close(figure)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_profile_chart()
    draw_growth_chart()
    print("charts saved to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
