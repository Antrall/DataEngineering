"""
Профилирование: время и пиковая память для каждого способа.
Запуск (из корня HW3): python src/profile.py [число_запусков]
"""
import csv
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil


SRC_DIR = Path(__file__).parent
RESULTS_PATH = Path("results/profile_results.csv")
SAMPLING_INTERVAL_SECONDS = 0.02

JOBS = [
    ("MapReduce v1 (before optimization)", ["mapreduce_v1.py"]),
    ("MapReduce (optimized, 4 processes)", ["mapreduce.py"]),
    ("MapReduce (optimized, 1 process)", ["mapreduce.py", "--workers", "1", "--reducers", "1"]),
    ("DuckDB SQL", ["duckdb_sql.py"]),
]


def measure_process_tree_memory(process):
    total = process.memory_info().rss
    for child in process.children(recursive=True):
        try:
            total += child.memory_info().rss
        except psutil.NoSuchProcess:
            pass

    return total


def run_once(command):
    process = psutil.Popen(
        [sys.executable] + command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    peak_memory = 0
    stop_sampling = threading.Event()

    def sample_memory():
        nonlocal peak_memory
        while not stop_sampling.is_set():
            try:
                peak_memory = max(peak_memory, measure_process_tree_memory(process))
            except psutil.NoSuchProcess:
                break
            time.sleep(SAMPLING_INTERVAL_SECONDS)

    sampler = threading.Thread(target=sample_memory)
    start_time = time.time()
    sampler.start()

    exit_code = process.wait()
    elapsed_seconds = time.time() - start_time
    stop_sampling.set()
    sampler.join()

    if exit_code != 0:
        raise SystemExit(f"{command} exited with code {exit_code}")

    return elapsed_seconds, peak_memory / 1024 / 1024


def main():
    run_count = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    measurements = []
    for job_name, arguments in JOBS:
        command = [str(SRC_DIR / arguments[0])] + arguments[1:]
        for run_number in range(1, run_count + 1):
            elapsed_seconds, peak_memory_mib = run_once(command)
            print(
                f"{job_name:36s} run {run_number}: {elapsed_seconds:6.1f} s, "
                f"peak memory {peak_memory_mib:7.0f} MiB",
                flush=True,
            )
            measurements.append([job_name, run_number, round(elapsed_seconds, 2), round(peak_memory_mib, 1)])

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["method", "run", "time_s", "peak_mem_mib"])
        writer.writerows(measurements)

    print("\naverage over runs:")
    for job_name, _ in JOBS:
        times = [row[2] for row in measurements if row[0] == job_name]
        memories = [row[3] for row in measurements if row[0] == job_name]
        print(
            f"{job_name:36s} time {statistics.mean(times):6.1f} s (min {min(times):.1f}, max {max(times):.1f}), "
            f"memory {statistics.mean(memories):7.0f} MiB (max {max(memories):.0f})"
        )


if __name__ == "__main__":
    main()
