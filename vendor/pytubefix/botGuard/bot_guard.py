import os
import subprocess
import sys
from kivy.utils import platform

PLATFORM = sys.platform

if platform != "android":
    import nodejs_wheel.executable

    NODE_DIR = nodejs_wheel.executable.ROOT_DIR
else:
    NODE_DIR = None


def _node_path() -> str:
    if platform == "android":
        from android_node import configure

        return configure()["node"]["path"]

    suffix = ".exe" if os.name == "nt" else ""
    bin_dir = NODE_DIR if os.name == "nt" else os.path.join(NODE_DIR, "bin")
    return os.path.join(bin_dir, "node" + suffix)


NODE_PATH = _node_path()
VM_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'vm/botGuard.js')

def generate_po_token(video_id: str) -> str:
    """
    Run nodejs to generate poToken through botGuard.

    """
    try:
        result = subprocess.check_output(
            [NODE_PATH, VM_PATH, video_id],
            stderr=subprocess.PIPE
        ).decode()
        return result.replace("\n", "")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Failed to execute botGuard.js: {e.stderr.decode().strip()}"
        ) from e
