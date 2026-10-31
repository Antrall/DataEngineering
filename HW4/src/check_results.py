"""
Проверка результатов: указатель на результат в ZooKeeper и сравнение результата каждой эпохи с результатом HW3
Запуск (из корня HW4): python src/check_results.py [--run-id pairs]
"""
import argparse
import json

from kazoo.client import KazooClient

import common
from coordinator import POINTER_PATH


HW3_RESULT_KEY = "results/mapreduce/skills_2.csv"


def print_pointer(zk_hosts, log=print):
    client = KazooClient(hosts=zk_hosts)
    client.start()
    value, stat = client.get(POINTER_PATH)
    client.stop()

    log(f"result pointer: version {stat.version}, data {value.decode('utf-8')}")
    return json.loads(value) if value else None


def compare_with_hw3(s3_client, run_id, log=print):
    expected = common.read_text_object(s3_client, HW3_RESULT_KEY)
    response = s3_client.list_objects_v2(Bucket=common.BUCKET_NAME, Prefix=f"hw4/{run_id}/epoch-")

    all_match = True
    for stored_object in response.get("Contents", []):
        actual = common.read_text_object(s3_client, stored_object["Key"])
        matches = actual == expected
        all_match = all_match and matches
        row_count = actual.count("\n") - 1
        log(f"{stored_object['Key']}: {row_count} rows, matches HW3 result: {matches}")

    return all_match


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="pairs")
    parser.add_argument("--zk-hosts", default="localhost:2181,localhost:2182,localhost:2183")
    args = parser.parse_args()

    print_pointer(args.zk_hosts)
    compare_with_hw3(common.create_s3_client(), args.run_id)


if __name__ == "__main__":
    main()
