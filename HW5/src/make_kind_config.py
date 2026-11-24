import argparse
import subprocess
from pathlib import Path


TEMPLATE = """kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: hw5
nodes:
  - role: control-plane
  - role: worker
    kubeadmConfigPatches:
      - |
        kind: JoinConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            system-reserved: "cpu={reserved_cpu}"
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-cpu", type=int, default=2, help="CPUs left to workloads on the worker node")
    parser.add_argument("--out", default="kind-config.yaml")
    args = parser.parse_args()

    cpu_count = int(subprocess.run(
        ["docker", "info", "--format", "{{.NCPU}}"], capture_output=True, text=True, check=True,
    ).stdout)
    reserved_cpu = max(0, cpu_count - args.keep_cpu)

    Path(args.out).write_text(TEMPLATE.format(reserved_cpu=reserved_cpu), encoding="utf-8")
    print(f"host CPUs: {cpu_count}, reserved on the worker: {reserved_cpu}, left for workloads: {cpu_count - reserved_cpu}")
    print("written:", args.out)


if __name__ == "__main__":
    main()
