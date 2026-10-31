"""
Расчёт частот пар навыков по одному чанку CSV (логика мапера из HW3).
"""
import csv
from collections import Counter
from itertools import combinations

import common


def split_into_chunks(object_size, chunk_bytes):
    return [
        (chunk_index, start_offset, min(start_offset + chunk_bytes, object_size))
        for chunk_index, start_offset in enumerate(range(0, object_size, chunk_bytes))
    ]


def count_pairs_in_chunk(client, chunk, object_size, column_indices, skill_aliases):
    chunk_index, start_offset, end_offset = chunk
    role_bytes = common.VARIANT_ROLE.encode("utf-8")

    lines = common.read_chunk_lines(client, start_offset, end_offset, object_size)
    if chunk_index == 0:
        lines = lines[1:]  # заголовок файла

    pair_counts = Counter()
    for line in lines:
        if role_bytes not in line:
            continue

        row = next(csv.reader([line.decode("utf-8")]))
        if row[column_indices["role"]] != common.VARIANT_ROLE:
            continue

        skills = set()
        for raw_skill in row[column_indices["key_skills"]].split(","):
            skill = common.normalize_skill(raw_skill, skill_aliases)
            if skill:
                skills.add(skill)

        pair_counts.update(combinations(sorted(skills), 2))

    return pair_counts
