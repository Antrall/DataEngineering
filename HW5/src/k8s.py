import json
import re
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from string import Template


CONTEXT = "kind-hw5"
NAMESPACE = "hw5"
IMAGE = "hw5-pairs:1"
MANIFESTS_DIR = Path(__file__).resolve().parent.parent / "manifests"
LOGS_DIR = Path("logs")
IN_CLUSTER_S3 = "http://rustfs.hw5.svc.cluster.local:9000"
PORT_FORWARD_PORT = 19000


class StageLog:
    def __init__(self, name):
        LOGS_DIR.mkdir(exist_ok=True)
        self.file = open(LOGS_DIR / f"{name}.txt", "w", encoding="utf-8")

    def __call__(self, message=""):
        for line in str(message).split("\n"):
            print(line, flush=True)
            self.file.write(line + "\n")
        self.file.flush()

    def command(self, *args):
        shown = [f'"{arg}"' if any(char in arg for char in " ()") else arg for arg in args]
        self("> kubectl " + " ".join(shown))
        output = kubectl(*args, check=False).rstrip("\n")
        for line in output.split("\n"):
            print(line, flush=True)
            self.file.write(line + "\n")
        self.file.flush()
        return output


def run(command, input_text=None, check=True):
    result = subprocess.run(command, input=input_text, capture_output=True, text=True, encoding="utf-8")
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)}: {result.stderr.strip()}")
    return result.stdout + ("" if check else result.stderr)


def kubectl(*args, input_text=None, check=True):
    return run(["kubectl", "--context", CONTEXT, *args], input_text=input_text, check=check)


def kubectl_json(*args):
    return json.loads(kubectl(*args, "-o", "json"))


def render(manifest_name, **values):
    template = Template((MANIFESTS_DIR / manifest_name).read_text(encoding="utf-8"))
    return template.substitute(values)


def apply(text):
    return kubectl("apply", "-f", "-", input_text=text)


def host_s3_endpoint():
    system = run(["docker", "info", "--format", "{{.OperatingSystem}}"]).strip()
    if "Docker Desktop" in system:
        return "http://host.docker.internal:9000"

    gateway = run(["docker", "network", "inspect", "kind", "--format", "{{(index .IPAM.Config 0).Gateway}}"]).strip()
    return f"http://{gateway}:9000"


def wait_until(condition, timeout_seconds, interval_seconds=1.0, description="condition"):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(interval_seconds)
    raise TimeoutError(f"timeout waiting for {description}")


def job_pods(job_name, namespace=NAMESPACE):
    return kubectl_json("get", "pods", "-n", namespace, "-l", f"job-name={job_name}")["items"]


def describe_pod_status(pod):
    statuses = pod["status"].get("containerStatuses") or [{}]
    terminated = statuses[0].get("state", {}).get("terminated") or {}
    return {
        "name": pod["metadata"]["name"],
        "phase": pod["status"].get("phase"),
        "reason": terminated.get("reason"),
        "exit_code": terminated.get("exitCode"),
        "node": pod["spec"].get("nodeName"),
    }


def delete_job(job_name, namespace=NAMESPACE):
    kubectl("delete", "job", job_name, "-n", namespace, "--ignore-not-found", "--wait=true", check=False)


def parse_time(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


@contextmanager
def port_forward_to_rustfs():
    process = subprocess.Popen(
        ["kubectl", "--context", CONTEXT, "port-forward", "-n", NAMESPACE, "svc/rustfs", f"{PORT_FORWARD_PORT}:9000"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(3)
        yield f"http://localhost:{PORT_FORWARD_PORT}"
    finally:
        process.terminate()
        process.wait()


PEAK_PATTERN = re.compile(r"peak memory: cgroup (\d+|n/a) MiB, maxrss (\d+) MiB")


def parse_peak(pod_log):
    match = PEAK_PATTERN.search(pod_log)
    if not match:
        return None
    return {"cgroup": match.group(1), "maxrss": int(match.group(2))}


def job_duration_seconds(job_name, namespace=NAMESPACE):
    def completed_status():
        status = kubectl_json("get", "job", job_name, "-n", namespace)["status"]
        return status if "completionTime" in status or status.get("failed") else None

    status = wait_until(completed_status, 30, description=f"status of {job_name}")
    if "completionTime" not in status:
        return None
    return (parse_time(status["completionTime"]) - parse_time(status["startTime"])).total_seconds()


def run_single_job(
    log,
    job_name,
    endpoint,
    memory_limit_mib,
    output_prefix,
    cpu_request="250m",
    chunk_delay="0",
    priority_class="",
    namespace=NAMESPACE,
    timeout_seconds=300,
):
    delete_job(job_name, namespace)
    apply(render(
        "job-single.yaml",
        JOB_NAME=job_name,
        NAMESPACE=namespace,
        S3_ENDPOINT=endpoint,
        CPU_REQUEST=cpu_request,
        MEMORY_LIMIT=f"{memory_limit_mib}Mi",
        OUTPUT_PREFIX=output_prefix,
        PRIORITY_CLASS=priority_class,
        CHUNK_DELAY=chunk_delay,
    ))

    def finished_pod():
        pods = job_pods(job_name, namespace)
        return pods[0] if pods and pods[0]["status"].get("phase") in ("Succeeded", "Failed") else None

    pod = wait_until(finished_pod, timeout_seconds, description=f"pod of {job_name}")
    status = describe_pod_status(pod)
    pod_log = kubectl("logs", status["name"], "-n", namespace, check=False)
    peak = parse_peak(pod_log)

    outcome = status["reason"] or status["phase"]
    log(f"{job_name}: limit {memory_limit_mib}Mi: phase {status['phase']}, container {outcome}, "
        f"exit code {status['exit_code']}"
        + (f", peak cgroup {peak['cgroup']} MiB, maxrss {peak['maxrss']} MiB" if peak else ""))
    return status, peak, pod_log, job_duration_seconds(job_name, namespace)


WORKER_NODE = "hw5-worker"


def parse_cpu_millicores(value):
    return int(value[:-1]) if value.endswith("m") else int(float(value) * 1000)


def free_cpu_millicores():
    node = kubectl_json("get", "node", WORKER_NODE)
    allocatable = parse_cpu_millicores(node["status"]["allocatable"]["cpu"])
    pods = kubectl_json("get", "pods", "-A", "--field-selector", f"spec.nodeName={WORKER_NODE}")["items"]

    requested = 0
    for pod in pods:
        if pod["status"].get("phase") in ("Succeeded", "Failed"):
            continue
        for container in pod["spec"]["containers"]:
            requested += parse_cpu_millicores(container.get("resources", {}).get("requests", {}).get("cpu", "0"))
    return allocatable, requested, allocatable - requested


def pod_phase_counts(pods):
    counts = {}
    for pod in pods:
        phase = pod["status"].get("phase", "Unknown")
        counts[phase] = counts.get(phase, 0) + 1
    return counts


def event_lines(namespace, reasons, since=None):
    events = kubectl_json("get", "events", "-n", namespace)["items"]
    rows = []
    for event in events:
        if event.get("reason") not in reasons:
            continue
        stamp = event.get("eventTime") or event.get("lastTimestamp") or event["metadata"]["creationTimestamp"]
        moment = datetime.strptime(stamp[:19], "%Y-%m-%dT%H:%M:%S")
        if since and moment < since:
            continue
        involved = event["involvedObject"]
        rows.append((moment, event["reason"], f"{involved['kind'].lower()}/{involved['name']}", event.get("message", "")))
    return sorted(rows)


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def node_allocation_block():
    text = kubectl("describe", "node", WORKER_NODE, check=False)
    start = text.index("Allocated resources:")
    end = text.index("Events:", start)
    return text[start:end].strip()
