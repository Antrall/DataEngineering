import argparse
import json
import os
import resource
import signal
import sys
import time
from collections import Counter

import DataEngineering.HW5.src.common as common
from DataEngineering.HW5.src.pair_counter import count_pairs_in_chunk, split_into_chunks


SKILL_SEPARATOR = "|"
CGROUP_PEAK_FILES = (
    "/sys/fs/cgroup/memory.peak",
    "/sys/fs/cgroup/memory/memory.max_usage_in_bytes",
)
BYTES_IN_MIB = 1024 * 1024


def read_peak_memory_report():
    cgroup_peak = "n/a"
    for path in CGROUP_PEAK_FILES:
        if os.path.exists(path):
            with open(path, encoding="ascii") as file:
                cgroup_peak = f"{int(file.read()) / BYTES_IN_MIB:.0f}"
            break

    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return f"peak memory: cgroup {cgroup_peak} MiB, maxrss {max_rss:.0f} MiB"


def prepare_context(args):
    client = common.create_s3_client()
    object_size = common.get_object_size(client)
    header = common.read_csv_header(client)
    column_indices = {"role": header.index("role"), "key_skills": header.index("key_skills")}
    skill_aliases = common.load_skill_aliases(client)
    chunks = split_into_chunks(object_size, args.chunk_mb * BYTES_IN_MIB)
    return client, object_size, column_indices, skill_aliases, chunks


def sorted_rows(pair_counts):
    ordered = sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))
    return [list(pair) + [count] for pair, count in ordered]


def write_result(client, output_prefix, pair_counts):
    key = f"{output_prefix}/skills_2.csv"
    common.write_csv_object(client, key, ["skill_1", "skill_2", "vacancies"], sorted_rows(pair_counts))
    print(f"result written: {common.BUCKET_NAME}/{key}, {len(pair_counts)} pairs")


def print_top(pair_counts, count=10):
    print(f"top-{count} pairs:")
    for skill_1, skill_2, vacancies in sorted_rows(pair_counts)[:count]:
        print(f"  {skill_1} + {skill_2}: {vacancies}")


def run_whole(args):
    client, object_size, column_indices, skill_aliases, chunks = prepare_context(args)
    print(f"object {common.RAW_DATA_KEY}: {object_size} bytes, {len(chunks)} chunks of {args.chunk_mb} MiB")

    pair_counts = Counter()
    for chunk in chunks:
        pair_counts.update(count_pairs_in_chunk(client, chunk, object_size, column_indices, skill_aliases))
        if args.chunk_delay:
            time.sleep(args.chunk_delay)
        print(f"chunk {chunk[0]} done ({chunk[0] + 1}/{len(chunks)})", flush=True)

    write_result(client, args.output_prefix, pair_counts)
    print_top(pair_counts)


def run_chunk(args):
    index = args.index if args.index is not None else int(os.environ["JOB_COMPLETION_INDEX"])
    client, object_size, column_indices, skill_aliases, chunks = prepare_context(args)

    started = time.time()
    pair_counts = count_pairs_in_chunk(client, chunks[index], object_size, column_indices, skill_aliases)
    if args.hold_seconds:
        time.sleep(args.hold_seconds)

    partial = {SKILL_SEPARATOR.join(pair): count for pair, count in pair_counts.items()}
    key = f"{args.partials_prefix}/part-{index:04d}.json"
    common.write_object(client, key, json.dumps(partial).encode("utf-8"))
    print(f"chunk {index}/{len(chunks)}: {len(partial)} pairs in {time.time() - started:.1f} s, written to {key}")


def run_reduce(args):
    client = common.create_s3_client()
    paginator = client.get_paginator("list_objects_v2")

    pair_counts = Counter()
    parts = 0
    for page in paginator.paginate(Bucket=common.BUCKET_NAME, Prefix=f"{args.partials_prefix}/"):
        for stored_object in page.get("Contents", []):
            partial = json.loads(common.read_text_object(client, stored_object["Key"]))
            for key, count in partial.items():
                pair_counts[tuple(key.split(SKILL_SEPARATOR))] += count
            parts += 1
    print(f"partial results merged: {parts}")

    write_result(client, args.output_prefix, pair_counts)
    print_top(pair_counts)


def exit_on_sigterm(signal_number, frame):
    print("SIGTERM received, exiting", flush=True)
    sys.exit(143)


def main():
    signal.signal(signal.SIGTERM, exit_on_sigterm)

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("whole", "chunk", "reduce"), required=True)
    parser.add_argument("--chunk-mb", type=int, default=8)
    parser.add_argument("--index", type=int, help="chunk number; by default JOB_COMPLETION_INDEX is used")
    parser.add_argument("--output-prefix", default="k8s/result")
    parser.add_argument("--partials-prefix", default="k8s/partials")
    parser.add_argument("--chunk-delay", type=float, default=0.0, help="pause after each chunk in whole mode, seconds")
    parser.add_argument("--hold-seconds", type=float, default=0.0, help="pause in chunk mode before writing, seconds")
    args = parser.parse_args()

    {"whole": run_whole, "chunk": run_chunk, "reduce": run_reduce}[args.mode](args)
    print(read_peak_memory_report())


if __name__ == "__main__":
    main()
