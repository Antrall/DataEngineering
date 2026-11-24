import time

import DataEngineering.HW5.src.k8s as k8s


NAMESPACE = "hw5-quota"
JOB_NAME = "quota-job"
COMPLETIONS = 10
PARALLELISM = 8
CPU_REQUEST = "250m"
HOLD_SECONDS = 10
GREEDY_POD_MANIFEST = "manifests/greedy-pod.yaml"


def quota_usage():
    quota = k8s.kubectl_json("get", "resourcequota", "hw5-quota", "-n", NAMESPACE)["status"]
    return {name: f"{quota['used'][name]}/{quota['hard'][name]}" for name in quota["hard"]}


def main():
    log = k8s.StageLog("stage5_quota")
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "namespace.yaml"))
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "quota.yaml"))
    k8s.delete_job(JOB_NAME, NAMESPACE)
    log.command("describe", "resourcequota", "hw5-quota", "-n", NAMESPACE)

    log("== a pod that alone exceeds the quota is rejected at once")
    log.command("apply", "-f", GREEDY_POD_MANIFEST)

    log(f"== Job: {COMPLETIONS} pods of {CPU_REQUEST}, {PARALLELISM} at a time, each works {HOLD_SECONDS} s")
    started = k8s.utc_now()
    k8s.apply(k8s.render(
        "job-parallel.yaml",
        JOB_NAME=JOB_NAME,
        NAMESPACE=NAMESPACE,
        S3_ENDPOINT=k8s.IN_CLUSTER_S3,
        COMPLETIONS=COMPLETIONS,
        PARALLELISM=PARALLELISM,
        CPU_REQUEST=CPU_REQUEST,
        MEMORY_REQUEST="64Mi",
        MEMORY_LIMIT="96Mi",
        HOLD_SECONDS=HOLD_SECONDS,
        PARTIALS_PREFIX="k8s/quota",
        PRIORITY_CLASS="",
    ))
    time.sleep(7)
    log.command("get", "pods", "-n", NAMESPACE)
    log.command("describe", "resourcequota", "hw5-quota", "-n", NAMESPACE)
    log("> kubectl get events -n hw5-quota   (FailedCreate)")
    for _moment, reason, target, message in k8s.event_lines(NAMESPACE, {"FailedCreate"}, since=started)[:2]:
        log(f"  {reason} {target}: {message[:230]}")

    log("== timeline: pods by phase and quota usage")
    previous = None
    deadline = time.time() + 240
    while time.time() < deadline:
        counts = k8s.pod_phase_counts(k8s.job_pods(JOB_NAME, NAMESPACE))
        state = (counts, quota_usage()["requests.cpu"], quota_usage()["pods"])
        if state != previous:
            log(f"t+{(k8s.utc_now() - started).total_seconds():4.0f} s: pods {counts}, "
                f"quota requests.cpu {state[1]}, pods {state[2]}")
            previous = state
        status = k8s.kubectl_json("get", "job", JOB_NAME, "-n", NAMESPACE)["status"]
        if status.get("succeeded", 0) >= COMPLETIONS:
            break
        time.sleep(1)

    created_failures = k8s.event_lines(NAMESPACE, {"FailedCreate"}, since=started)
    log("== summary")
    log(f"FailedCreate events (quota refused to create a pod): {len(created_failures)}")
    log(f"all {COMPLETIONS} pods completed anyway: the Job kept retrying while the quota freed up")


if __name__ == "__main__":
    main()
