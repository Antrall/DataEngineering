import csv
import time
from pathlib import Path

import DataEngineering.HW5.src.k8s as k8s


JOB_NAME = "cpu-wait"
CPU_REQUEST_M = 500
WAITING_PODS = 3
HOLD_SECONDS = 12
MEMORY_LIMIT_MIB = 96


def pod_times(pod):
    created = k8s.parse_time(pod["metadata"]["creationTimestamp"])
    scheduled = next((k8s.parse_time(c["lastTransitionTime"]) for c in pod["status"].get("conditions", [])
                      if c["type"] == "PodScheduled" and c["status"] == "True"), None)
    return created, scheduled


def save_pod_times(started_at):
    rows = []
    for pod in k8s.job_pods(JOB_NAME):
        created, scheduled = pod_times(pod)
        finished = k8s.parse_time(pod["status"]["containerStatuses"][0]["state"]["terminated"]["finishedAt"])
        index = int(pod["metadata"]["annotations"]["batch.kubernetes.io/job-completion-index"])
        rows.append([index] + [round((moment - started_at).total_seconds()) for moment in (created, scheduled, finished)])

    Path("results").mkdir(exist_ok=True)
    with open(Path("results") / "stage3_pods.csv", "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["index", "created_s", "scheduled_s", "finished_s"])
        writer.writerows(sorted(rows))


def main():
    log = k8s.StageLog("stage3_cpu_wait")
    allocatable, requested, free = k8s.free_cpu_millicores()
    fit = free // CPU_REQUEST_M
    parallelism = fit + WAITING_PODS
    completions = parallelism * 2
    log(f"worker node: allocatable {allocatable}m CPU, already requested by system pods {requested}m, free {free}m")
    log(f"each pod asks {CPU_REQUEST_M}m -> {fit} pods fit at once; the Job wants {parallelism} at once, "
        f"{completions} pods in total")

    k8s.delete_job(JOB_NAME)
    started = k8s.utc_now()
    k8s.apply(k8s.render(
        "job-parallel.yaml",
        JOB_NAME=JOB_NAME,
        NAMESPACE=k8s.NAMESPACE,
        S3_ENDPOINT=k8s.IN_CLUSTER_S3,
        COMPLETIONS=completions,
        PARALLELISM=parallelism,
        CPU_REQUEST=f"{CPU_REQUEST_M}m",
        MEMORY_REQUEST="64Mi",
        MEMORY_LIMIT=f"{MEMORY_LIMIT_MIB}Mi",
        HOLD_SECONDS=HOLD_SECONDS,
        PARTIALS_PREFIX="k8s/cpu-wait",
        PRIORITY_CLASS="",
    ))

    log("== pods right after the start")
    time.sleep(6)
    log.command("get", "pods", "-n", k8s.NAMESPACE, "-l", f"job-name={JOB_NAME}", "-o", "wide")
    pending = [pod for pod in k8s.job_pods(JOB_NAME) if pod["status"]["phase"] == "Pending"]
    if pending:
        describe = k8s.kubectl("describe", "pod", pending[0]["metadata"]["name"], "-n", k8s.NAMESPACE, check=False)
        log("> kubectl describe pod " + pending[0]["metadata"]["name"] + " -n hw5   (Events)")
        log(describe[describe.index("Events:"):].strip())
    log("> kubectl describe node " + k8s.WORKER_NODE + "   (Allocated resources)")
    log(k8s.node_allocation_block())

    log("== timeline: number of pods by phase")
    previous = None
    deadline = time.time() + 300
    while time.time() < deadline:
        pods = k8s.job_pods(JOB_NAME)
        counts = k8s.pod_phase_counts(pods)
        if counts != previous:
            log(f"t+{(k8s.utc_now() - started).total_seconds():4.0f} s: {counts}")
            previous = counts
        status = k8s.kubectl_json("get", "job", JOB_NAME, "-n", k8s.NAMESPACE)["status"]
        if status.get("succeeded", 0) >= completions:
            break
        time.sleep(1)

    log("== waiting time of each pod: creation -> scheduling")
    waits = []
    for pod in sorted(k8s.job_pods(JOB_NAME), key=lambda p: int(p["metadata"]["annotations"]["batch.kubernetes.io/job-completion-index"])):
        created, scheduled = pod_times(pod)
        wait = (scheduled - created).total_seconds() if scheduled else None
        waits.append(wait)
        log(f"  pod index {pod['metadata']['annotations']['batch.kubernetes.io/job-completion-index']:>2s}: "
            f"waited {wait:3.0f} s before it got CPU")

    save_pod_times(started_at=min(pod_times(pod)[0] for pod in k8s.job_pods(JOB_NAME)))

    log("== scheduler events (FailedScheduling)")
    rows = k8s.event_lines(k8s.NAMESPACE, {"FailedScheduling"}, since=started)
    log(f"FailedScheduling events: {len(rows)}; the first message:\n  {rows[0][3] if rows else '-'}")

    log("== summary")
    immediate = sum(1 for wait in waits if wait is not None and wait <= 2)
    log(f"pods scheduled immediately after creation: {immediate} of {completions}")
    log(f"pods that waited for CPU: {completions - immediate}; longest wait {max(waits):.0f} s")
    status = k8s.kubectl_json("get", "job", JOB_NAME, "-n", k8s.NAMESPACE)["status"]
    duration = (k8s.parse_time(status["completionTime"]) - k8s.parse_time(status["startTime"])).total_seconds()
    rounds = completions // parallelism
    log(f"Job finished in {duration:.0f} s; without the CPU shortage ({parallelism} pods at once) it would take about "
        f"{rounds} rounds of ~{HOLD_SECONDS + 3} s = ~{rounds * (HOLD_SECONDS + 3)} s")


if __name__ == "__main__":
    main()
