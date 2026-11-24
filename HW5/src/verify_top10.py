import csv
import io
import sys
from pathlib import Path

import boto3
from botocore.config import Config

import DataEngineering.HW5.src.common as common


REFERENCE_PATH = Path("results") / "reference" / "hw3_skills_2.csv"


def create_client(endpoint_url):
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=common.ACCESS_KEY,
        aws_secret_access_key=common.SECRET_KEY,
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


def compare_with_hw3(endpoint_url, prefix):
    client = create_client(endpoint_url)
    actual = common.read_text_object(client, f"{prefix}/skills_2.csv")
    expected = REFERENCE_PATH.read_text(encoding="utf-8")

    actual_rows = list(csv.reader(io.StringIO(actual)))
    expected_rows = list(csv.reader(io.StringIO(expected)))
    return actual == expected, actual_rows[:11] == expected_rows[:11], actual_rows[1:11]


def main():
    prefix = sys.argv[1]
    endpoint_url = sys.argv[2] if len(sys.argv) > 2 else common.ENDPOINT_URL
    same_file, same_top10, top10 = compare_with_hw3(endpoint_url, prefix)

    print(f"{prefix}/skills_2.csv vs HW3: file identical: {same_file}, top-10 identical: {same_top10}")
    for skill_1, skill_2, vacancies in top10:
        print(f"  {skill_1} + {skill_2}: {vacancies}")


if __name__ == "__main__":
    main()
