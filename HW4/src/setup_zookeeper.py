"""
Раскладывает конфигурации по трём копиям ZooKeeper (zk/server1..3) и создаёт файлы myid.
Запуск (из корня HW4): python src/setup_zookeeper.py
"""
import shutil
from pathlib import Path


SERVER_IDS = (1, 2, 3)


def main():
    for server_id in SERVER_IDS:
        server_dir = Path("zk") / f"server{server_id}"
        data_dir = server_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy(Path("zookeeper") / f"server{server_id}.cfg", server_dir / "conf" / "zoo.cfg")
        (data_dir / "myid").write_text(f"{server_id}\n", encoding="ascii")
        print(f"server{server_id}: conf/zoo.cfg copied, data/myid = {server_id}")


if __name__ == "__main__":
    main()
