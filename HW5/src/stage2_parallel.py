import os
import subprocess
import sys
import time
from pathlib import Path

import DataEngineering.HW5.src.k8s as k8s
from DataEngineering.HW5.src.verify_top10 import compare_with_hw3, create_client


MEMORY_LIMIT_MIB = 96
CHUNK_COUNT = 34
PARALLELISM = 4
HEAVY_SECONDS = 4


def deploy_rustfs(log):
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "namespace.yaml"))
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "priority-classes.yaml"))
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "rustfs.yaml"))
    log(k8s.kubectl("rollout", "status", "deployment/rustfs", "-n", k8s.NAMESPACE, "--timeout=240s").strip())
    log.command("get", "deployment,pod,svc,pvc", "-n", k8s.NAMESPACE)


def upload_dataset(log, forward_url):
    log("uploading the dataset into the in-cluster S3 through port-forward")
    environment = {**os.environ, "S3_ENDPOINT": forward_url}
    result = subprocess.run(
        [sys.executable, "-m", "DataEngineering.HW5.src.upload"],
        capture_output=True, text=True, env=environment, check=True,
    )
    log(result.stdout.strip())


def delete_prefix(forward_url, prefix):
    client = create_client(forward_url)
    listing = client.list_objects_v2(Bucket="hh-lake", Prefix=prefix + "/")
    keys = [{"Key": stored_object["Key"]} for stored_object in listing.get("Contents", [])]
    if keys:
        client.delete_objects(Bucket="hh-lake", Delete={"Objects": keys})


def wait_job_finished(job_name, timeout_seconds):
    def finished():
        status = k8s.kubectl_json("get", "job", job_name, "-n", k8s.NAMESPACE)["status"]
        return status if status.get("succeeded", 0) >= CHUNK_COUNT or status.get("failed", 0) > 20 else None

    return k8s.wait_until(finished, timeout_seconds, interval_seconds=2, description=job_name)


def run_parallel(log, name, parallelism, hold_seconds, forward_url, show_pods=False):
    job_name = f"pairs-{name}"
    partials = f"k8s/partials-{name}"
    k8s.delete_job(job_name)
    delete_prefix(forward_url, partials)

    k8s.apply(k8s.render(
        "job-parallel.yaml",
        JOB_NAME=job_name,
        NAMESPACE=k8s.NAMESPACE,
        S3_ENDPOINT=k8s.IN_CLUSTER_S3,
        COMPLETIONS=CHUNK_COUNT,
        PARALLELISM=parallelism,
        CPU_REQUEST="250m",
        MEMORY_REQUEST="64Mi",
        MEMORY_LIMIT=f"{MEMORY_LIMIT_MIB}Mi",
        HOLD_SECONDS=hold_seconds,
        PARTIALS_PREFIX=partials,
        PRIORITY_CLASS="",
    ))
    log(f"{job_name}: {CHUNK_COUNT} pods, {parallelism} at a time, pause per chunk {hold_seconds} s")
    if show_pods:
        time.sleep(5)
        log.command("get", "job", job_name, "-n", k8s.NAMESPACE)
        log.command("get", "pods", "-n", k8s.NAMESPACE, "-l", f"job-name={job_name}")

    wait_job_finished(job_name, 900)
    duration = k8s.job_duration_seconds(job_name)
    pod_logs = k8s.kubectl("logs", "-n", k8s.NAMESPACE, "-l", f"job-name={job_name}", "--tail=1",
                           "--max-log-requests=64", check=False)
    peaks = [int(peak["cgroup"]) for line in pod_logs.split("\n") if (peak := k8s.parse_peak(line))]
    log(f"{job_name}: all {CHUNK_COUNT} chunk pods finished in {duration:.0f} s; "
        f"peak memory of pods: max {max(peaks)} MiB (limit {MEMORY_LIMIT_MIB} MiB), pods with a peak line: {len(peaks)}")

    reduce_name = f"reduce-{name}"
    k8s.delete_job(reduce_name)
    k8s.apply(k8s.render(
        "job-reduce.yaml",
        JOB_NAME=reduce_name,
        NAMESPACE=k8s.NAMESPACE,
        S3_ENDPOINT=k8s.IN_CLUSTER_S3,
        PARTIALS_PREFIX=partials,
        OUTPUT_PREFIX=f"k8s/result-{name}",
    ))
    k8s.wait_until(lambda: k8s.job_pods(reduce_name) and k8s.job_pods(reduce_name)[0]["status"]["phase"] == "Succeeded",
                   120, description=reduce_name)
    same_file, same_top10, _ = compare_with_hw3(forward_url, f"k8s/result-{name}")
    log(f"{reduce_name}: merged; vs HW3: file identical {same_file}, top-10 identical {same_top10}")
    return duration, max(peaks), same_file


def export_result(log, forward_url, prefix):
    client = create_client(forward_url)
    text = client.get_object(Bucket="hh-lake", Key=f"{prefix}/skills_2.csv")["Body"].read().decode("utf-8")
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)
    (results_dir / "k8s_skills_2.csv").write_text(text, encoding="utf-8")
    (results_dir / "k8s_top10.csv").write_text("\n".join(text.split("\n")[:11]) + "\n", encoding="utf-8")
    same = (results_dir / "k8s_top10.csv").read_text(encoding="utf-8") == (results_dir / "reference" / "hw3_top10.csv").read_text(encoding="utf-8")
    log(f"results/k8s_skills_2.csv and results/k8s_top10.csv saved; top-10 identical to results/reference/hw3_top10.csv: {same}")


def main():
    log = k8s.StageLog("stage2_parallel")
    deploy_rustfs(log)

    with k8s.port_forward_to_rustfs() as forward_url:
        upload_dataset(log, forward_url)
        rows = []

        log("== single pod, in-cluster S3")
        status, peak, _, duration = k8s.run_single_job(
            log, "pairs-single", k8s.IN_CLUSTER_S3, MEMORY_LIMIT_MIB, "k8s/stage2-single")
        same_file, _, _ = compare_with_hw3(forward_url, "k8s/stage2-single")
        rows.append(("1 pod (whole file)", 0, duration, int(peak["cgroup"]), same_file))

        log("== parallel Jobs, real data")
        duration, peak_mib, same_file = run_parallel(log, "p4", PARALLELISM, 0, forward_url)
        rows.append((f"{CHUNK_COUNT} pods, {PARALLELISM} at a time", 0, duration, peak_mib, same_file))

        log(f"== heavy chunks: pause of {HEAVY_SECONDS} s per chunk")
        status, peak, _, duration = k8s.run_single_job(
            log, "pairs-single", k8s.IN_CLUSTER_S3, MEMORY_LIMIT_MIB, "k8s/stage2-single-heavy",
            chunk_delay=str(HEAVY_SECONDS), timeout_seconds=900)
        same_file, _, _ = compare_with_hw3(forward_url, "k8s/stage2-single-heavy")
        rows.append(("1 pod (whole file)", HEAVY_SECONDS, duration, int(peak["cgroup"]), same_file))

        for parallelism in (2, PARALLELISM):
            duration, peak_mib, same_file = run_parallel(
                log, f"h{parallelism}", parallelism, HEAVY_SECONDS, forward_url, show_pods=parallelism == PARALLELISM)
            rows.append((f"{CHUNK_COUNT} pods, {parallelism} at a time", HEAVY_SECONDS, duration, peak_mib, same_file))

        export_result(log, forward_url, f"k8s/result-h{PARALLELISM}")

    log("== summary")
    log(f"{'variant':32s} {'pause, s':>9s} {'time, s':>8s} {'peak, MiB':>10s} {'equals HW3':>11s}")
    for variant, pause, duration, peak_mib, same_file in rows:
        log(f"{variant:32s} {pause:>9d} {duration:>8.0f} {peak_mib:>10d} {str(same_file):>11s}")


if __name__ == "__main__":
    main()
