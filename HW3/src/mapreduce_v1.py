"""
Первая версия MapReduce (до оптимизации).
Запуск (из корня HW3): python src/mapreduce_v1.py
"""
import csv
import time
import zlib
from collections import Counter
from itertools import combinations

import common


CHUNK_BYTES = 32 * 1024 * 1024
REDUCER_COUNT = 4
SKILL_SEPARATOR = "|"
STACK_SIZES = (1, 2, 3)
CSV_HEADERS = {
    1: ["skill"],
    2: ["skill_1", "skill_2"],
    3: ["skill_1", "skill_2", "skill_3"],
}


def main():
    start_time = time.time()
    client = common.create_s3_client()
    skill_aliases = common.load_skill_aliases(client)
    object_size = common.get_object_size(client)

    header = common.read_csv_header(client)
    role_column = header.index("role")
    skills_column = header.index("key_skills")

    run_id = f"mrv1-{int(start_time)}"
    chunks = [
        (chunk_index, start_offset, min(start_offset + CHUNK_BYTES, object_size))
        for chunk_index, start_offset in enumerate(range(0, object_size, CHUNK_BYTES))
    ]
    print(f"chunks: {len(chunks)}")

    vacancy_count = 0
    for chunk_index, start_offset, end_offset in chunks:
        lines = common.read_chunk_lines(client, start_offset, end_offset, object_size)
        if chunk_index == 0:
            lines = lines[1:]  # заголовок файла

        partition_lines = [[] for _ in range(REDUCER_COUNT)]
        for row in csv.reader(line.decode("utf-8") for line in lines):
            if row[role_column] != common.VARIANT_ROLE:
                continue
            vacancy_count += 1

            skills = set()
            for raw_skill in row[skills_column].split(","):
                skill = common.normalize_skill(raw_skill, skill_aliases)
                if skill:
                    skills.add(skill)

            sorted_skills = sorted(skills)
            for stack_size in STACK_SIZES:
                for skill_combination in combinations(sorted_skills, stack_size):
                    key = SKILL_SEPARATOR.join(skill_combination)
                    partition = zlib.crc32(key.encode("utf-8")) % REDUCER_COUNT
                    partition_lines[partition].append(f"{stack_size}\t{key}\t1\n")

        for partition in range(REDUCER_COUNT):
            common.write_object(
                client,
                f"tmp/{run_id}/map-{chunk_index:04d}-r{partition}",
                "".join(partition_lines[partition]).encode("utf-8"),
            )
        print(f"[map {chunk_index}] done")

    totals_by_stack_size = {stack_size: Counter() for stack_size in STACK_SIZES}
    for partition in range(REDUCER_COUNT):
        for chunk_index, _, _ in chunks:
            body = common.read_text_object(client, f"tmp/{run_id}/map-{chunk_index:04d}-r{partition}")
            for line in body.splitlines():
                stack_size, key, count = line.split("\t")
                totals_by_stack_size[int(stack_size)][tuple(key.split(SKILL_SEPARATOR))] += int(count)
        print(f"[reduce {partition}] done")

    for stack_size, totals in totals_by_stack_size.items():
        rows = sorted(totals.items(), key=lambda row: (-row[1], row[0]))
        common.write_csv_object(
            client,
            f"results/mapreduce_v1/skills_{stack_size}.csv",
            CSV_HEADERS[stack_size] + ["vacancies"],
            [list(skills) + [count] for skills, count in rows],
        )
        print(f"results/mapreduce_v1/skills_{stack_size}.csv: {len(rows)} rows")

    response = client.list_objects_v2(Bucket=common.BUCKET_NAME, Prefix=f"tmp/{run_id}/")
    keys = [stored_object["Key"] for stored_object in response["Contents"]]
    client.delete_objects(
        Bucket=common.BUCKET_NAME,
        Delete={"Objects": [{"Key": key} for key in keys]},
    )
    print(f"variant vacancies: {vacancy_count}, done in {time.time() - start_time:.1f} s")


if __name__ == "__main__":
    main()
