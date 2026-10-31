"""
Сценарий этапов 3 и 4: две копии координатора, лидер ставится на паузу посреди расчёта.
1. запускается координатор A, он становится лидером и считает чанки;
2. запускается координатор B, он ждёт;
3. после заданного числа чанков процесс лидера приостанавливается (psutil: suspend);
4. сессия лидера в ZooKeeper истекает через тайм-аут, B становится лидером и доделывает расчёт с чекпоинта;
5. когда прошло нужное время паузы, лидер возобновляется и пытается записать результат второй раз.

Запуск (из корня HW4):
    python src/run_failover.py --scenario without-fencing
    $env:FENCING = "1"; python src/run_failover.py --scenario with-fencing
"""
import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
from kazoo.client import KazooClient
from kazoo.exceptions import NoNodeError

import common
from check_results import compare_with_hw3, print_pointer


SRC_DIR = Path(__file__).parent
POLL_INTERVAL_SECONDS = 0.2
LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


class Scenario:
    def __init__(self, args):
        self.args = args
        self.log_dir = Path("logs") / args.scenario
        self.log_dir.mkdir(parents=True, exist_ok=True)
        for old_log in self.log_dir.glob("*.log"):
            old_log.unlink()
        self.orchestrator_log = open(self.log_dir / "orchestrator.log", "w", encoding="utf-8")

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{timestamp} [orchestrator] {message}"
        print(line, flush=True)
        self.orchestrator_log.write(line + "\n")
        self.orchestrator_log.flush()

    def reset_state(self):
        client = KazooClient(hosts=self.args.zk_hosts)
        client.start()
        try:
            client.delete("/hw4", recursive=True)
        except NoNodeError:
            pass
        client.stop()

        s3_client = common.create_s3_client()
        response = s3_client.list_objects_v2(Bucket=common.BUCKET_NAME, Prefix=f"hw4/{self.args.run_id}/")
        keys = [{"Key": stored_object["Key"]} for stored_object in response.get("Contents", [])]
        if keys:
            s3_client.delete_objects(Bucket=common.BUCKET_NAME, Delete={"Objects": keys})
        self.log(f"state reset: ZooKeeper /hw4 removed, {len(keys)} objects removed from the bucket")

    def start_coordinator(self, name):
        command = [
            sys.executable, str(SRC_DIR / "coordinator.py"),
            "--name", name,
            "--zk-hosts", self.args.zk_hosts,
            "--session-timeout", str(self.args.session_timeout),
            "--run-id", self.args.run_id,
            "--chunk-delay", str(self.args.chunk_delay),
            "--log-file", str(self.log_dir / f"coordinator-{name}.log"),
        ]
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log(f"coordinator {name} started")

        return process

    def read_log(self, name):
        path = self.log_dir / f"coordinator-{name}.log"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def wait_for_log_line(self, name, pattern, timeout_seconds):
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            for line in self.read_log(name).splitlines():
                if re.search(pattern, line):
                    return datetime.strptime(line[:23], LOG_TIME_FORMAT)
            time.sleep(POLL_INTERVAL_SECONDS)

        raise TimeoutError(f"coordinator {name}: no log line matching {pattern!r} in {timeout_seconds} s")

    def wait_for_exit(self, process, name, timeout_seconds):
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError(f"coordinator {name} did not exit in {timeout_seconds} s") from error

    def write_timeline(self):
        key_events = re.compile(
            r"started|became leader|resuming|wrote result|rejected|SUSPENDED|LOST|paused|resumed|result pointer"
        )
        lines = []
        for log_name in ("orchestrator.log", "coordinator-A.log", "coordinator-B.log"):
            for line in (self.log_dir / log_name).read_text(encoding="utf-8").splitlines():
                if key_events.search(line):
                    lines.append(line)

        lines.sort(key=lambda line: line[:23])
        (self.log_dir / "timeline.log").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run(self):
        args = self.args
        self.log(f"scenario {args.scenario}, FENCING={os.environ.get('FENCING', '0')}")
        self.reset_state()

        leader = self.start_coordinator("A")
        self.wait_for_log_line("A", r"became leader", 30)
        standby = self.start_coordinator("B")
        self.wait_for_log_line("B", r"waiting for leadership", 30)

        self.wait_for_log_line("A", rf"chunk \d+ done \({args.pause_after_chunks}/", 120)
        leader_process = psutil.Process(leader.pid)
        pause_time = datetime.now()
        leader_process.suspend()
        self.log(f"leader A paused after {args.pause_after_chunks} chunks")

        became_leader_time = self.wait_for_log_line("B", r"became leader", 60)
        failover_seconds = (became_leader_time - pause_time).total_seconds()
        self.log(f"standby B became leader {failover_seconds:.1f} s after the pause")

        self.wait_for_exit(standby, "B", 180)
        standby_finished = datetime.now()
        self.log(f"standby B finished, exit code {standby.returncode}")

        remaining = args.pause_seconds - (standby_finished - pause_time).total_seconds()
        if remaining > 0:
            time.sleep(remaining)
        paused_seconds = (datetime.now() - pause_time).total_seconds()
        leader_process.resume()
        self.log(f"leader A resumed after a pause of {paused_seconds:.0f} s")

        self.wait_for_exit(leader, "A", 180)
        self.log(f"leader A finished, exit code {leader.returncode}")

        print_pointer(args.zk_hosts, self.log)
        compare_with_hw3(common.create_s3_client(), args.run_id, self.log)
        self.log(f"summary: leader changed {failover_seconds:.1f} s after the pause, pause lasted {paused_seconds:.0f} s")
        self.orchestrator_log.close()
        self.write_timeline()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, help="name of the log folder, e.g. without-fencing")
    parser.add_argument("--zk-hosts", default="localhost:2181,localhost:2182,localhost:2183")
    parser.add_argument("--session-timeout", type=float, default=10)
    parser.add_argument("--run-id", default="pairs")
    parser.add_argument("--chunk-delay", type=float, default=0.6)
    parser.add_argument("--pause-after-chunks", type=int, default=16)
    parser.add_argument("--pause-seconds", type=float, default=40)
    args = parser.parse_args()

    Scenario(args).run()


if __name__ == "__main__":
    main()
