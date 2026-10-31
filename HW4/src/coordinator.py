"""
Координатор расчёта пар навыков (расчёт из HW3).
Запуск (из корня HW4): python src/coordinator.py --name A [--chunk-delay 1.0]
"""
import argparse
import json
import logging
import os
import time
from collections import Counter

from kazoo.client import KazooClient
from kazoo.exceptions import (
    BadVersionError,
    ConnectionClosedError,
    ConnectionLoss,
    NodeExistsError,
    SessionExpiredError,
)
from kazoo.recipe.election import Election

import common
from pair_counter import count_pairs_in_chunk, split_into_chunks


ROOT_PATH = "/hw4"
ELECTION_PATH = f"{ROOT_PATH}/election"
EPOCH_PATH = f"{ROOT_PATH}/epoch"
POINTER_PATH = f"{ROOT_PATH}/result_pointer"

SKILL_SEPARATOR = "|"
RECONNECT_ATTEMPTS = 40
RECONNECT_PAUSE_SECONDS = 1.0


class Coordinator:
    def __init__(self, args):
        self.name = args.name
        self.run_id = args.run_id
        self.chunk_bytes = args.chunk_mb * 1024 * 1024
        self.chunk_delay = args.chunk_delay
        self.fencing = os.environ.get("FENCING") == "1"

        self.logger = logging.getLogger(self.name)
        self.client = KazooClient(hosts=args.zk_hosts, timeout=args.session_timeout)
        self.log_states = True
        self.client.add_listener(self.log_connection_state)
        self.s3_client = common.create_s3_client()

        self.checkpoint_key = f"hw4/{self.run_id}/checkpoint.json"

    def log_connection_state(self, state):
        if self.log_states:
            self.logger.info("ZooKeeper connection state: %s", state)

    def call_zookeeper(self, operation, *args, **kwargs):
        for attempt in range(1, RECONNECT_ATTEMPTS + 1):
            try:
                return operation(*args, **kwargs)
            except (ConnectionLoss, SessionExpiredError, ConnectionClosedError) as error:
                self.logger.warning("ZooKeeper call failed (%s), attempt %d", type(error).__name__, attempt)
                time.sleep(RECONNECT_PAUSE_SECONDS)

        raise RuntimeError("ZooKeeper is not available")

    def ensure_nodes(self):
        self.client.ensure_path(ELECTION_PATH)
        for path, initial_value in ((EPOCH_PATH, b"0"), (POINTER_PATH, b"")):
            try:
                self.client.create(path, initial_value)
            except NodeExistsError:
                pass

    def run(self):
        self.client.start()
        self.logger.info(
            "started, session id 0x%x, FENCING=%s",
            self.client.client_id[0],
            "1" if self.fencing else "0",
        )
        self.ensure_nodes()

        self.logger.info("waiting for leadership")
        election = Election(self.client, ELECTION_PATH, identifier=self.name)
        try:
            election.run(self.lead)
        except Exception as error:
            self.logger.warning("election cleanup failed: %s", type(error).__name__)

        self.log_states = False
        self.client.stop()
        self.logger.info("exiting")

    def take_next_epoch(self):
        while True:
            value, stat = self.call_zookeeper(self.client.get, EPOCH_PATH)
            epoch = int(value) + 1
            try:
                new_stat = self.call_zookeeper(
                    self.client.set, EPOCH_PATH, str(epoch).encode(), version=stat.version,
                )
                return epoch, new_stat.version
            except BadVersionError:
                continue

    def load_checkpoint(self):
        try:
            body = common.read_text_object(self.s3_client, self.checkpoint_key)
        except self.s3_client.exceptions.NoSuchKey:
            return None

        return json.loads(body)

    def save_checkpoint(self, epoch, done_chunks, pair_counts):
        checkpoint = {
            "epoch": epoch,
            "done_chunks": sorted(done_chunks),
            "pair_counts": {SKILL_SEPARATOR.join(pair): count for pair, count in pair_counts.items()},
        }
        common.write_object(self.s3_client, self.checkpoint_key, json.dumps(checkpoint).encode("utf-8"))

    def lead(self):
        epoch, epoch_version = self.take_next_epoch()
        self.logger.info("became leader, epoch %d", epoch)

        pointer_value, _ = self.call_zookeeper(self.client.get, POINTER_PATH)
        if pointer_value:
            self.logger.info("result is already published, nothing to do")
            return

        object_size = common.get_object_size(self.s3_client)
        header = common.read_csv_header(self.s3_client)
        column_indices = {"role": header.index("role"), "key_skills": header.index("key_skills")}
        skill_aliases = common.load_skill_aliases(self.s3_client)
        chunks = split_into_chunks(object_size, self.chunk_bytes)

        done_chunks = set()
        pair_counts = Counter()
        checkpoint = self.load_checkpoint()
        if checkpoint:
            done_chunks = set(checkpoint["done_chunks"])
            for key, count in checkpoint["pair_counts"].items():
                pair_counts[tuple(key.split(SKILL_SEPARATOR))] = count
            self.logger.info(
                "resuming from checkpoint written by epoch %d: %d of %d chunks done",
                checkpoint["epoch"],
                len(done_chunks),
                len(chunks),
            )
        else:
            self.logger.info("no checkpoint, starting from scratch: %d chunks", len(chunks))

        for chunk in chunks:
            chunk_index = chunk[0]
            if chunk_index in done_chunks:
                continue

            pair_counts.update(count_pairs_in_chunk(self.s3_client, chunk, object_size, column_indices, skill_aliases))
            time.sleep(self.chunk_delay)

            done_chunks.add(chunk_index)
            self.save_checkpoint(epoch, done_chunks, pair_counts)
            self.logger.info(
                "chunk %d done (%d/%d), checkpoint saved",
                chunk_index,
                len(done_chunks),
                len(chunks),
            )

        self.publish(epoch, epoch_version, pair_counts)

    def publish(self, epoch, epoch_version, pair_counts):
        rows = sorted(pair_counts.items(), key=lambda item: (-item[1], item[0]))
        result_key = f"hw4/{self.run_id}/epoch-{epoch}/skills_2.csv"
        common.write_csv_object(
            self.s3_client,
            result_key,
            ["skill_1", "skill_2", "vacancies"],
            [list(pair) + [count] for pair, count in rows],
        )

        pointer = json.dumps({
            "epoch": epoch,
            "writer": self.name,
            "result_key": result_key,
        }).encode("utf-8")

        if self.fencing:
            self.publish_with_fencing(epoch, epoch_version, pointer)
        else:
            stat = self.call_zookeeper(self.client.set, POINTER_PATH, pointer)
            self.logger.info("epoch %d: wrote result %s, pointer version %d", epoch, result_key, stat.version)

    def publish_with_fencing(self, epoch, epoch_version, pointer):
        def commit_transaction():
            transaction = self.client.transaction()
            transaction.check(EPOCH_PATH, version=epoch_version)
            transaction.set_data(POINTER_PATH, pointer)
            return transaction.commit()

        results = self.call_zookeeper(commit_transaction)
        failures = [result for result in results if isinstance(result, BadVersionError)]
        if failures:
            self.logger.error(
                "epoch %d: publish rejected: BadVersionError, epoch node changed (a newer leader exists)",
                epoch,
            )
            return

        pointer_stat = results[1]
        self.logger.info("epoch %d: wrote result, pointer version %d", epoch, pointer_stat.version)


def configure_logging(name, log_file):
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file, mode="w", encoding="utf-8"))

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logging.getLogger("kazoo").setLevel(logging.WARNING)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="coordinator name used in logs and in the election")
    parser.add_argument("--zk-hosts", default="localhost:2181,localhost:2182,localhost:2183")
    parser.add_argument("--session-timeout", type=float, default=10)
    parser.add_argument("--run-id", default="pairs")
    parser.add_argument("--chunk-mb", type=int, default=8)
    parser.add_argument("--chunk-delay", type=float, default=0.6, help="artificial delay after each chunk, seconds")
    parser.add_argument("--log-file")
    args = parser.parse_args()

    configure_logging(args.name, args.log_file)
    Coordinator(args).run()


if __name__ == "__main__":
    main()
