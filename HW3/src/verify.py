"""
Сравнивает результаты двух способов построчно. По умолчанию сравниваются results/mapreduce и results/duckdb.
Запуск (из корня HW3): python src/verify.py [каталог_1 каталог_2]
"""
import csv
import io
import sys

import common


STACK_TITLES = {1: "skills", 2: "pairs", 3: "triples"}


def load_rows(client, directory, stack_size):
    text = common.read_text_object(client, f"{directory}/skills_{stack_size}.csv")
    rows = list(csv.reader(io.StringIO(text)))[1:]  # без заголовка

    return [tuple(row[:-1]) + (int(row[-1]),) for row in rows]


def main():
    first_directory = sys.argv[1] if len(sys.argv) > 2 else "results/mapreduce"
    second_directory = sys.argv[2] if len(sys.argv) > 2 else "results/duckdb"
    client = common.create_s3_client()

    all_match = True
    for stack_size, title in STACK_TITLES.items():
        first_rows = load_rows(client, first_directory, stack_size)
        second_rows = load_rows(client, second_directory, stack_size)

        matches = first_rows == second_rows
        all_match = all_match and matches

        first_total = sum(row[-1] for row in first_rows)
        second_total = sum(row[-1] for row in second_rows)
        verdict = "MATCH" if matches else "MISMATCH"
        print(
            f"{title:7s}: {first_directory}={len(first_rows)} rows, {second_directory}={len(second_rows)} rows, "
            f"frequency sum {first_total} / {second_total} -> {verdict}"
        )

        if not matches:
            differing_rows = set(first_rows) ^ set(second_rows)
            print("  differing rows:", len(differing_rows), list(differing_rows)[:5])

    print("RESULT:", "results match completely" if all_match else "MISMATCH FOUND")
    sys.exit(0 if all_match else 1)


if __name__ == "__main__":
    main()
