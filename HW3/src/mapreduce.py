"""
MapReduce поверх объектного хранилища (оптимизированная версия).
Запуск (из корня HW3): python src/mapreduce.py [--chunk-mb 8] [--workers 4] [--reducers 4] [--inject-fail 3]
"""
import argparse
import csv
import json
import sys
import time
import zlib

from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations

import common


MAX_ATTEMPTS = 3
SKILL_SEPARATOR = "|"
STACK_SIZES = (1, 2, 3)

CSV_HEADERS = {
    1: ["skill"],
    2: ["skill_1", "skill_2"],
    3: ["skill_1", "skill_2", "skill_3"],
}


def run_map_task(
    chunk_index,
    attempt,
    start_offset,
    end_offset,
    object_size,
    run_id,
    reducer_count,
    column_indices,
    failing_chunk_index,
):
    client = common.create_s3_client()
    skill_aliases = common.load_skill_aliases(client)
    role_bytes = common.VARIANT_ROLE.encode("utf-8")
    role_column = column_indices["role"]
    skills_column = column_indices["key_skills"]

    lines = common.read_chunk_lines(client, start_offset, end_offset, object_size)
    if chunk_index == 0:
        lines = lines[1:]

    normalization_cache = {}
    partition_counters = [Counter() for _ in range(reducer_count)]
    stats = {
        "rows_scanned": len(lines),
        "vacancies": 0,
        "emitted_1": 0,
        "emitted_2": 0,
        "emitted_3": 0,
    }

    for line in lines:
        if role_bytes not in line:
            continue

        row = next(csv.reader([line.decode("utf-8")]))
        if row[role_column] != common.VARIANT_ROLE:
            continue
        stats["vacancies"] += 1

        skills = set()
        for raw_skill in row[skills_column].split(","):
            skill = normalization_cache.get(raw_skill)
            if skill is None:
                skill = common.normalize_skill(raw_skill, skill_aliases) or ""
                normalization_cache[raw_skill] = skill
            if skill:
                skills.add(skill)

        sorted_skills = sorted(skills)
        for stack_size in STACK_SIZES:
            for skill_combination in combinations(sorted_skills, stack_size):
                key = SKILL_SEPARATOR.join(skill_combination)
                partition = zlib.crc32(key.encode("utf-8")) % reducer_count
                partition_counters[partition][(stack_size, key)] += 1
                stats[f"emitted_{stack_size}"] += 1

    for partition, counter in enumerate(partition_counters):
        body = "".join(
            f"{stack_size}\t{key}\t{count}\n"
            for (stack_size, key), count in counter.items()
        )
        common.write_object(
            client,
            f"tmp/{run_id}/map-{chunk_index:04d}-a{attempt}-r{partition}",
            body.encode("utf-8"),
        )

        if failing_chunk_index == chunk_index and attempt == 1 and partition == 0:
            raise RuntimeError(f"mapper {chunk_index}: process killed (injected failure)")

    return chunk_index, attempt, stats


def run_reduce_task(partition, committed_attempts, run_id):
    client = common.create_s3_client()

    totals = Counter()
    for chunk_index, attempt in committed_attempts.items():
        key = f"tmp/{run_id}/map-{chunk_index:04d}-a{attempt}-r{partition}"
        body = common.read_text_object(client, key)
        for line in body.splitlines():
            stack_size, skills_key, count = line.split("\t")
            totals[(int(stack_size), skills_key)] += int(count)

    body = "".join(
        f"{stack_size}\t{key}\t{count}\n"
        for (stack_size, key), count in totals.items()
    )
    common.write_object(client, f"tmp/{run_id}/reduce-r{partition}", body.encode("utf-8"))

    return partition, len(totals)


def run_map_phase(chunks, object_size, run_id, args, column_indices):
    committed_attempts = {}
    total_stats = Counter()

    with ProcessPoolExecutor(args.workers) as pool:
        pending = {}
        for chunk_index, start_offset, end_offset in chunks:
            future = pool.submit(
                run_map_task, chunk_index, 1, start_offset, end_offset, object_size,
                run_id, args.reducers, column_indices, args.inject_fail,
            )
            pending[future] = (chunk_index, 1, start_offset, end_offset)

        while pending:
            for future in as_completed(list(pending)):
                chunk_index, attempt, start_offset, end_offset = pending.pop(future)
                try:
                    _, finished_attempt, stats = future.result()
                    committed_attempts[chunk_index] = finished_attempt
                    total_stats.update(stats)
                except Exception as error:
                    print(f"[map {chunk_index:03d}] attempt {attempt} failed: {error}")
                    if attempt >= MAX_ATTEMPTS:
                        sys.exit(f"chunk {chunk_index} was not processed in {MAX_ATTEMPTS} attempts")

                    print(f"[map {chunk_index:03d}] retrying, attempt {attempt + 1}")
                    retry = pool.submit(
                        run_map_task, chunk_index, attempt + 1, start_offset, end_offset, object_size,
                        run_id, args.reducers, column_indices, -1,
                    )
                    pending[retry] = (chunk_index, attempt + 1, start_offset, end_offset)
                break

    return committed_attempts, total_stats


def run_reduce_phase(committed_attempts, run_id, reducer_count):
    with ProcessPoolExecutor(reducer_count) as pool:
        futures = [
            pool.submit(run_reduce_task, partition, committed_attempts, run_id)
            for partition in range(reducer_count)
        ]
        for future in as_completed(futures):
            partition, unique_keys = future.result()
            print(f"[reduce {partition}] unique keys: {unique_keys}")


def write_final_results(client, run_id, reducer_count, output_prefix):
    rows_by_stack_size = {stack_size: [] for stack_size in STACK_SIZES}
    for partition in range(reducer_count):
        body = common.read_text_object(client, f"tmp/{run_id}/reduce-r{partition}")
        for line in body.splitlines():
            stack_size, key, count = line.split("\t")
            skills = tuple(key.split(SKILL_SEPARATOR))
            rows_by_stack_size[int(stack_size)].append((skills, int(count)))

    for stack_size, rows in rows_by_stack_size.items():
        rows.sort(key=lambda row: (-row[1], row[0]))
        common.write_csv_object(
            client,
            f"{output_prefix}/skills_{stack_size}.csv",
            CSV_HEADERS[stack_size] + ["vacancies"],
            [list(skills) + [count] for skills, count in rows],
        )
        print(f"{output_prefix}/skills_{stack_size}.csv: {len(rows)} rows")

    return {stack_size: len(rows) for stack_size, rows in rows_by_stack_size.items()}


def delete_intermediate_objects(client, run_id):
    response = client.list_objects_v2(Bucket=common.BUCKET_NAME, Prefix=f"tmp/{run_id}/")
    keys = [stored_object["Key"] for stored_object in response.get("Contents", [])]

    for batch_start in range(0, len(keys), 1000):
        batch = keys[batch_start:batch_start + 1000]
        client.delete_objects(
            Bucket=common.BUCKET_NAME,
            Delete={"Objects": [{"Key": key} for key in batch]},
        )
    print(f"removed intermediate objects: {len(keys)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-mb", type=int, default=8)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reducers", type=int, default=4)
    parser.add_argument("--inject-fail", type=int, default=-1,
        help="index of the chunk whose mapper fails on the first attempt")
    parser.add_argument("--out", default="results/mapreduce")
    parser.add_argument("--keep-tmp", action="store_true")
    args = parser.parse_args()

    start_time = time.time()
    client = common.create_s3_client()
    object_size = common.get_object_size(client)
    header = common.read_csv_header(client)
    column_indices = {
        "role": header.index("role"),
        "key_skills": header.index("key_skills"),
    }

    chunk_bytes = args.chunk_mb * 1024 * 1024
    chunks = [
        (chunk_index, start_offset, min(start_offset + chunk_bytes, object_size))
        for chunk_index, start_offset in enumerate(range(0, object_size, chunk_bytes))
    ]
    run_id = f"mr-{int(start_time)}"
    print(
        f"object {common.RAW_DATA_KEY}: {object_size} bytes, {len(chunks)} chunks of {args.chunk_mb} MiB, "
        f"{args.workers} parallel mappers, {args.reducers} reducers"
    )

    committed_attempts, stats = run_map_phase(chunks, object_size, run_id, args, column_indices)
    print(
        f"map finished in {time.time() - start_time:.1f} s: "
        f"rows scanned {stats['rows_scanned']}, variant vacancies {stats['vacancies']}"
    )

    run_reduce_phase(committed_attempts, run_id, args.reducers)
    unique_counts = write_final_results(client, run_id, args.reducers, args.out)

    summary = {
        "rows_scanned": stats["rows_scanned"],
        "vacancies": stats["vacancies"],
        "chunks": len(chunks),
        "unique": unique_counts,
        "emitted": {stack_size: stats[f"emitted_{stack_size}"] for stack_size in STACK_SIZES},
    }
    
    common.write_object(
        client,
        f"{args.out}/summary.json",
        json.dumps(summary, ensure_ascii=False, indent=2).encode("utf-8"),
    )

    if not args.keep_tmp:
        delete_intermediate_objects(client, run_id)
    print(f"done in {time.time() - start_time:.1f} s")


if __name__ == "__main__":
    main()
