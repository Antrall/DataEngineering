import csv
import re
from pathlib import Path

import matplotlib


matplotlib.use("Agg")
import matplotlib.pyplot as plt


OUTPUT_DIR = Path("report") / "images"
BAR_COLOR = "#4c78a8"
LIGHT_BAR_COLOR = "#9ecae9"
WAIT_COLOR = "#e45756"
RUN_COLOR = "#54a24b"
SUMMARY_ROW = re.compile(r"^\d\d:\d\d:\d\d (1 pod \(whole file\)|34 pods, \d at a time)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\w+)$")


def read_stage2_rows():
    rows = []
    for line in Path("logs/stage2_parallel.txt").read_text(encoding="utf-8").splitlines():
        match = SUMMARY_ROW.match(line)
        if match:
            variant, pause, duration, peak, _ = match.groups()
            rows.append((variant, int(pause), int(duration)))
    return rows


def draw_stage2_chart():
    rows = read_stage2_rows()
    labels = [f"{variant.replace('34 pods, ', '34 pods,\\n')}\\n(pause {pause} s)" for variant, pause, _ in rows]
    durations = [duration for _, _, duration in rows]
    colors = [BAR_COLOR if pause == 0 else LIGHT_BAR_COLOR for _, pause, _ in rows]

    figure, axis = plt.subplots(figsize=(9, 3.8))
    axis.bar(range(len(rows)), durations, color=colors)
    axis.set_xticks(range(len(rows)))
    axis.set_xticklabels(labels, fontsize=8)
    for position, duration in enumerate(durations):
        axis.text(position, duration, str(duration), ha="center", va="bottom", fontsize=9)
    axis.set_ylabel("time, s")
    axis.set_title("Stage 2: calculation time (dark: real chunks, light: heavy chunks)")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "stage2_times.png", dpi=130)
    plt.close(figure)


def draw_stage3_gantt():
    with open("results/stage3_pods.csv", encoding="utf-8") as file:
        rows = [[int(value) for value in row.values()] for row in csv.DictReader(file)]

    figure, axis = plt.subplots(figsize=(9, 4.2))
    for index, created, scheduled, finished in rows:
        axis.barh(index, scheduled - created, left=created, color=WAIT_COLOR, height=0.7)
        axis.barh(index, finished - scheduled, left=scheduled, color=RUN_COLOR, height=0.7)
    axis.invert_yaxis()
    axis.set_xlabel("seconds from the start of the Job")
    axis.set_ylabel("pod index")
    axis.set_title("Stage 3: red - waiting for CPU (Pending), green - running")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "stage3_gantt.png", dpi=130)
    plt.close(figure)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    draw_stage2_chart()
    draw_stage3_gantt()
    print("charts saved to", OUTPUT_DIR)


if __name__ == "__main__":
    main()
