"""
Общие настройки и функции.
"""
import csv
import io
import os

import boto3
from botocore.config import Config


ENDPOINT_URL = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "antrall")
SECRET_KEY = os.environ.get("S3_SECRET_KEY", "antrall123")

BUCKET_NAME = "hh-lake"
RAW_DATA_KEY = "raw/it_vacancies_2024.csv"
SKILL_ALIASES_KEY = "ref/skills_alias.csv"

VARIANT_ROLE = "Программист, разработчик на C и C++"
LINE_OVERLAP_BYTES = 64 * 1024


def create_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},
            retries={"max_attempts": 3},
        ),
    )


def read_text_object(client, key):
    response = client.get_object(Bucket=BUCKET_NAME, Key=key)
    return response["Body"].read().decode("utf-8")


def write_object(client, key, body):
    client.put_object(Bucket=BUCKET_NAME, Key=key, Body=body)


def write_csv_object(client, key, header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    write_object(client, key, buffer.getvalue().encode("utf-8"))


def load_skill_aliases(client):
    text = read_text_object(client, SKILL_ALIASES_KEY)
    reader = csv.DictReader(io.StringIO(text))
    return {row["alias"]: row["skill"] for row in reader}


def normalize_skill(raw_skill, skill_aliases):
    lowered = raw_skill.strip().lower()
    if not lowered:
        return None
    return skill_aliases.get(lowered, lowered)


def get_object_size(client, key=RAW_DATA_KEY):
    return client.head_object(Bucket=BUCKET_NAME, Key=key)["ContentLength"]


def read_csv_header(client):
    first_bytes = client.get_object(
        Bucket=BUCKET_NAME,
        Key=RAW_DATA_KEY,
        Range="bytes=0-8191",
    )["Body"].read()
    header_line = first_bytes.split(b"\n", 1)[0].decode("utf-8")
    return next(csv.reader([header_line]))


def read_chunk_lines(client, start_offset, end_offset, object_size):
    read_start = max(start_offset - 1, 0)
    read_end = min(end_offset + LINE_OVERLAP_BYTES, object_size) - 1
    response = client.get_object(
        Bucket=BUCKET_NAME,
        Key=RAW_DATA_KEY,
        Range=f"bytes={read_start}-{read_end}",
    )
    buffer = response["Body"].read()

    position = 0
    if start_offset > 0:
        position = buffer.find(b"\n") + 1
        if position == 0:
            return []

    line_start_limit = end_offset - read_start
    reached_object_end = read_end + 1 >= object_size

    lines = []
    while position < len(buffer) and position < line_start_limit:
        newline_position = buffer.find(b"\n", position)
        if newline_position == -1:
            if not reached_object_end:
                raise RuntimeError("line is longer than LINE_OVERLAP_BYTES, increase the overlap")
            newline_position = len(buffer)

        lines.append(buffer[position:newline_position])
        position = newline_position + 1

    return lines
