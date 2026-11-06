import hashlib
import shutil
from pathlib import Path
from urllib.request import urlretrieve
from zipfile import ZipFile

import os

from pythonforandroid.recipe import Recipe
os.environ["PIP_CONSTRAINT"] = str(
    Path(__file__).resolve().parents[2] / "build-constraints.txt"
)


class NodejsRecipe(Recipe):
    version = "26.12.1"
    depends = ["python3"]

    commit = "72d412bb906bf9dac74b62bef0d7ab28a8d177ce"

    files = {
        "libnode.so": (
            "03b66a1bc12376be196d06c9e749aab94" "e807077981c3e50b95b75d7e19542a1"
        ),
        "libnode.zip.so": (
            "e08e94b62cd17ae5b51b2eeba9ddd7327" "1b6bc2de01871201f15982bb841fa48"
        ),
    }

    def build_arch(self, arch):
        if arch.arch != "arm64-v8a":
            raise RuntimeError("This Node recipe supports arm64-v8a only")

        cache = Path(self.ctx.packages_path) / "nodejs" / self.commit
        cache.mkdir(parents=True, exist_ok=True)

        base = (
            "https://media.githubusercontent.com/media/"
            f"deniscerri/ytdlnis-packages/{self.commit}/"
            "nodejs_library/src/main/jniLibs/arm64-v8a"
        )

        for filename, expected in self.files.items():
            cached = cache / filename

            if not cached.exists():
                temporary = cache / (filename + ".download")
                urlretrieve(f"{base}/{filename}", temporary)

                actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
                if actual != expected:
                    temporary.unlink()
                    raise RuntimeError(f"Checksum failed: {filename}")

                temporary.replace(cached)

            actual = hashlib.sha256(cached.read_bytes()).hexdigest()
            if actual != expected:
                raise RuntimeError(f"Cached checksum failed: {cached}")

        target = Path(self.ctx.get_python_install_dir(arch.arch)) / "android_node"
        libraries = target / "lib"
        libraries.mkdir(parents=True, exist_ok=True)

        native_dir = Path(self.ctx.get_libs_dir(arch.arch))
        native_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache / "libnode.so", native_dir / "libnode_exec.so")

        with ZipFile(cache / "libnode.zip.so") as archive:
            for entry in archive.infolist():
                path = Path(entry.filename)

                if (
                    not entry.is_dir()
                    and path.parent.as_posix() == "usr/lib"
                    and "_node.so" in path.name
                ):
                    (libraries / path.name).write_bytes(archive.read(entry))

        shutil.copy2(
            Path(self.get_recipe_dir()) / "runtime.py",
            target / "__init__.py",
        )


recipe = NodejsRecipe()
