"""
Создаёт бакет hh-lake и загружает в него датасет и словарь синонимов навыков.
Запуск (из корня HW3): python src/upload.py [путь_к_csv]
"""
import sys
import time
from pathlib import Path

from boto3.s3.transfer import TransferConfig

import common


MULTIPART_PART_BYTES = 8 * 1024 * 1024


def main():
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/it_vacancies_2024.csv")
    aliases_path = Path("data/skills_alias.csv")
    client = common.create_s3_client()

    existing_buckets = [bucket["Name"] for bucket in client.list_buckets()["Buckets"]]
    if common.BUCKET_NAME not in existing_buckets:
        client.create_bucket(Bucket=common.BUCKET_NAME)
        print("bucket created:", common.BUCKET_NAME)

    start_time = time.time()
    transfer_config = TransferConfig(
        multipart_threshold=MULTIPART_PART_BYTES,
        multipart_chunksize=MULTIPART_PART_BYTES,
    )

    client.upload_file(str(csv_path), common.BUCKET_NAME, common.RAW_DATA_KEY, Config=transfer_config)
    client.upload_file(str(aliases_path), common.BUCKET_NAME, common.SKILL_ALIASES_KEY)
    print(f"uploaded {csv_path.stat().st_size} bytes in {time.time() - start_time:.1f} s")

    for stored_object in client.list_objects_v2(Bucket=common.BUCKET_NAME)["Contents"]:
        print(f"{stored_object['Key']:35s} {stored_object['Size']:>12d}")


if __name__ == "__main__":
    main()
