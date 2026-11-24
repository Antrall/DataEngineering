import subprocess
import sys
import tempfile
from pathlib import Path


ARCHITECTURES = {"x86_64": "amd64", "aarch64": "arm64"}
CLUSTER_NAME = "hw5"


def image_in_all_nodes(image):
    nodes = subprocess.run(["kind", "get", "nodes", "--name", CLUSTER_NAME], capture_output=True, text=True, check=True)
    return all(
        subprocess.run(["docker", "exec", node, "crictl", "inspecti", image], capture_output=True).returncode == 0
        for node in nodes.stdout.split()
    )


def main():
    architecture = subprocess.run(
        ["docker", "info", "--format", "{{.Architecture}}"], capture_output=True, text=True, check=True,
    ).stdout.strip()
    platform = f"linux/{ARCHITECTURES.get(architecture, architecture)}"

    for image in sys.argv[1:]:
        with tempfile.TemporaryDirectory() as directory:
            archive = str(Path(directory) / "image.tar")
            subprocess.run(["docker", "save", "--platform", platform, "-o", archive, image], check=True)
            result = subprocess.run(["kind", "load", "image-archive", archive, "--name", CLUSTER_NAME], capture_output=True, text=True)

        if result.returncode != 0:
            if not image_in_all_nodes(image):
                raise RuntimeError(f"kind load failed for {image}: {result.stderr.strip()[-300:]}")
            print(f"note: kind reported an error for the extra attestation manifest of {image}, the image itself is loaded")
        print(f"loaded into kind: {image} ({platform})")


if __name__ == "__main__":
    main()
