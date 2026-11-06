import os
from pathlib import Path

from jnius import autoclass


def configure():
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    native_dir = Path(activity.getApplicationInfo().nativeLibraryDir)
    executable = native_dir / "libnode_exec.so"

    if not executable.is_file():
        raise FileNotFoundError(f"Packaged Node executable missing: {executable}")

    library_path = str(Path(__file__).resolve().parent / "lib")
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    paths = existing.split(":") if existing else []

    if library_path not in paths:
        os.environ["LD_LIBRARY_PATH"] = ":".join([library_path, *paths])

    return {"node": {"path": str(executable)}}
