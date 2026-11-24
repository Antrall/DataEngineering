import time

import DataEngineering.HW5.src.k8s as k8s
from DataEngineering.HW5.src.verify_top10 import compare_with_hw3


LOW_JOB = "low-batch"
HIGH_JOB = "urgent-high"
LOW_REQUEST_M = 400
LOW_HOLD_SECONDS = 150
MEMORY_LIMIT_MIB = 96
BOTH_JOBS = "job-name in (low-batch,urgent-high)"
PODS_TABLE = "custom-columns=NAME:.metadata.name,PRIORITY:.spec.priorityClassName,CPU:.spec.containers[0].resources.requests.cpu,PHASE:.status.phase,NODE:.spec.nodeName"


def main():
    log = k8s.StageLog("stage4_preemption")
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "priority-classes.yaml"))
    log.command("get", "priorityclass", "batch-low", "urgent-high")

    for job in (LOW_JOB, HIGH_JOB):
        k8s.delete_job(job)
    allocatable, requested, free = k8s.free_cpu_millicores()
    low_count = free // LOW_REQUEST_M
    leftover = free - low_count * LOW_REQUEST_M
    high_request = leftover + LOW_REQUEST_M // 2
    log(f"free CPU {free}m: {low_count} background pods of {LOW_REQUEST_M}m take {low_count * LOW_REQUEST_M}m, "
        f"{leftover}m stay free; the urgent pod asks {high_request}m")

    k8s.apply(k8s.render(
        "job-parallel.yaml",
        JOB_NAME=LOW_JOB,
        NAMESPACE=k8s.NAMESPACE,
        S3_ENDPOINT=k8s.IN_CLUSTER_S3,
        COMPLETIONS=low_count,
        PARALLELISM=low_count,
        CPU_REQUEST=f"{LOW_REQUEST_M}m",
        MEMORY_REQUEST="64Mi",
        MEMORY_LIMIT=f"{MEMORY_LIMIT_MIB}Mi",
        HOLD_SECONDS=LOW_HOLD_SECONDS,
        PARTIALS_PREFIX="k8s/low-priority",
        PRIORITY_CLASS="batch-low",
    ))
    k8s.wait_until(lambda: k8s.pod_phase_counts(k8s.job_pods(LOW_JOB)).get("Running") == low_count, 120,
                   description="background pods")
    log("== before: the node is busy with background pods")
    log.command("get", "pods", "-n", k8s.NAMESPACE, "-l", f"job-name={LOW_JOB}", "-o", PODS_TABLE)

    log("== the urgent job is submitted")
    submitted = k8s.utc_now()
    k8s.apply(k8s.render(
        "job-single.yaml",
        JOB_NAME=HIGH_JOB,
        NAMESPACE=k8s.NAMESPACE,
        S3_ENDPOINT=k8s.IN_CLUSTER_S3,
        CPU_REQUEST=f"{high_request}m",
        MEMORY_LIMIT=f"{MEMORY_LIMIT_MIB}Mi",
        OUTPUT_PREFIX="k8s/urgent",
        PRIORITY_CLASS="urgent-high",
        CHUNK_DELAY="0.5",
    ))
    time.sleep(3)
    log("== 3 s later: one background pod is gone (preempted), the urgent pod already runs")
    log.command("get", "pods", "-n", k8s.NAMESPACE, "-l", BOTH_JOBS, "-o", "wide")
    k8s.wait_until(lambda: k8s.job_pods(HIGH_JOB) and k8s.job_pods(HIGH_JOB)[0]["status"]["phase"] == "Running",
                   120, interval_seconds=0.5, description="urgent pod running")
    log("== during: the urgent pod runs, the three other background pods continue")
    log.command("get", "pods", "-n", k8s.NAMESPACE, "-l", BOTH_JOBS, "-o", PODS_TABLE)
    k8s.wait_until(lambda: k8s.job_pods(HIGH_JOB)[0]["status"]["phase"] == "Succeeded",
                   180, interval_seconds=1, description="urgent job")

    log("== events: who was preempted and when (seconds after the urgent job was submitted)")
    reasons = {"FailedScheduling", "Preempted", "Scheduled", "Killing", "SuccessfulCreate"}
    for moment, reason, target, message in k8s.event_lines(k8s.NAMESPACE, reasons, since=submitted):
        if HIGH_JOB in target or reason in ("Preempted", "Killing") or (reason == "Scheduled" and HIGH_JOB in target):
            log(f"  t+{(moment - submitted).total_seconds():3.0f} s  {reason:16s} {target:34s} {message[:110]}")

    log("== after: the urgent pod finished, the Job created a new background pod instead of the preempted one")
    log.command("get", "pods", "-n", k8s.NAMESPACE, "-l", BOTH_JOBS, "-o", PODS_TABLE)
    urgent_pod = k8s.job_pods(HIGH_JOB)[0]
    log("urgent job log (tail):\n" + "\n".join(k8s.kubectl("logs", urgent_pod["metadata"]["name"], "-n", k8s.NAMESPACE).strip().split("\n")[-4:]))

    with k8s.port_forward_to_rustfs() as forward_url:
        same_file, same_top10, _ = compare_with_hw3(forward_url, "k8s/urgent")
    log(f"urgent result vs HW3: file identical {same_file}, top-10 identical {same_top10}")

    time.sleep(1)
    k8s.delete_job(LOW_JOB)
    log("background job deleted")


if __name__ == "__main__":
    main()
