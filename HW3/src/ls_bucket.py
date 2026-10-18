"""
Список объектов бакета hh-lake с размерами.
Запуск (из корня HW3): python src/ls_bucket.py
"""
import common


def main():
    client = common.create_s3_client()
    paginator = client.get_paginator("list_objects_v2")

    total_bytes = 0
    for page in paginator.paginate(Bucket=common.BUCKET_NAME):
        for stored_object in page.get("Contents", []):
            total_bytes += stored_object["Size"]
            modified = f"{stored_object['LastModified']:%Y-%m-%d %H:%M:%S}"
            print(f"{modified} {stored_object['Size']:>12d} {stored_object['Key']}")

    print(f"\nTotal Size: {total_bytes / 1024 / 1024:.1f} MiB")


if __name__ == "__main__":
    main()
