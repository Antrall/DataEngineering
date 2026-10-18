"""
Скачивает из хранилища всё, что лежит в results/, в локальную папку results/.
Запуск (из корня HW3): python src/export_results.py
"""
from pathlib import Path
import common


def main():
    client = common.create_s3_client()
    paginator = client.get_paginator("list_objects_v2")
    downloaded_count = 0
    
    for page in paginator.paginate(Bucket=common.BUCKET_NAME, Prefix="results/"):
        for stored_object in page.get("Contents", []):
            local_path = Path(stored_object["Key"])
            local_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(common.BUCKET_NAME, stored_object["Key"], str(local_path))
            downloaded_count += 1

    print(f"downloaded {downloaded_count} files into results/")


if __name__ == "__main__":
    main()
