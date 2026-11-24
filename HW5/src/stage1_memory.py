import math

import DataEngineering.HW5.src.k8s as k8s
from DataEngineering.HW5.src.verify_top10 import compare_with_hw3


JOB_NAME = "pairs-single"
OUTPUT_PREFIX = "k8s/stage1"
GENEROUS_LIMIT_MIB = 512
PROBE_LIMITS_MIB = (48, 64, 80)
HEADROOM = 1.25
ROUND_TO_MIB = 16
HOST_S3_FOR_CHECK = "http://localhost:9000"


def run_job(log, memory_limit_mib, endpoint):
    status, peak, pod_log, _ = k8s.run_single_job(log, JOB_NAME, endpoint, memory_limit_mib, OUTPUT_PREFIX)
    return status, peak, pod_log


def main():
    log = k8s.StageLog("stage1_memory")
    k8s.kubectl("apply", "-f", str(k8s.MANIFESTS_DIR / "namespace.yaml"))
    endpoint = k8s.host_s3_endpoint()
    log(f"external S3 (HW3 on the host), as seen from pods: {endpoint}")

    log("== A. generous limit: measure the peak")
    _, peak, pod_log = run_job(log, GENEROUS_LIMIT_MIB, endpoint)
    peak_mib = int(peak["cgroup"])
    log("pod log (tail):\n" + "\n".join(pod_log.strip().split("\n")[-4:]))

    log("== B. limits below the peak")
    results = []
    for limit in PROBE_LIMITS_MIB:
        status, _, _ = run_job(log, limit, endpoint)
        results.append((limit, status["reason"] or status["phase"]))
        if results[-1][1] == "OOMKilled" and len(results) == 1:
            log.command("get", "pods", "-n", k8s.NAMESPACE)
            describe = k8s.kubectl("describe", "pod", status["name"], "-n", k8s.NAMESPACE, check=False)
            keep = ("State:", "Reason:", "Exit Code:", "Limits:", "memory:", "Requests:", "cpu:")
            log("> kubectl describe pod " + status["name"] + " -n hw5   (selected lines)")
            log("\n".join(line for line in describe.split("\n") if line.strip().startswith(keep))[:600])

    chosen = math.ceil(peak_mib * HEADROOM / ROUND_TO_MIB) * ROUND_TO_MIB
    log(f"== C. chosen limit = ceil({peak_mib} MiB * {HEADROOM} / {ROUND_TO_MIB}) * {ROUND_TO_MIB} = {chosen} MiB")
    status, _, _ = run_job(log, chosen, endpoint)
    results.append((chosen, status["reason"] or status["phase"]))

    same_file, same_top10, top10 = compare_with_hw3(HOST_S3_FOR_CHECK, OUTPUT_PREFIX)
    log(f"result {OUTPUT_PREFIX}/skills_2.csv vs HW3: file identical {same_file}, top-10 identical {same_top10}")
    for skill_1, skill_2, vacancies in top10:
        log(f"  {skill_1} + {skill_2}: {vacancies}")

    log("== summary: limit -> result")
    log(f"measured peak (cgroup): {peak_mib} MiB")
    for limit, outcome in sorted(results):
        log(f"  {limit:>4} MiB -> {outcome}")


if __name__ == "__main__":
    main()
