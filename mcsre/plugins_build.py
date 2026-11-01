"""Build the benchmark's Paper plugins from plugins/src with javac."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "plugins" / "src"


def _classpath(server_dir):
    jars = sorted(str(p) for p in Path(server_dir, "libraries").rglob("*.jar"))
    if not jars:
        raise FileNotFoundError(f"no jars under {server_dir}/libraries; boot the server once first")
    return os.pathsep.join(jars)


def _build_one(src, jar, classpath):
    java_files = [str(p) for p in src.rglob("*.java")]
    resources = [p for p in src.iterdir() if p.is_file()]
    with tempfile.TemporaryDirectory() as tmp:
        classes = Path(tmp, "classes")
        subprocess.run(
            ["javac", "--release", "17", "-nowarn", "-encoding", "UTF-8",
             "-cp", classpath, "-d", str(classes), *java_files],
            check=True, capture_output=True, text=True,
        )
        partial = Path(tmp, jar.name)
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            for res in resources:
                z.write(res, res.name)
            for cls in sorted(classes.rglob("*.class")):
                z.write(cls, cls.relative_to(classes).as_posix())
        shutil.move(str(partial), str(jar))


def build_plugins(server_dir: str, out_dir: str) -> list[str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    classpath = None
    jars = []
    for src in sorted(p for p in SRC_ROOT.iterdir() if p.is_dir()):
        jar = out / f"{src.name}.jar"
        newest = max(p.stat().st_mtime for p in src.rglob("*") if p.is_file())
        if not jar.exists() or jar.stat().st_mtime <= newest:
            classpath = classpath or _classpath(server_dir)
            try:
                _build_one(src, jar, classpath)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"javac failed for {src.name}:\n{e.stderr}") from e
        jars.append(str(jar))
    return jars


if __name__ == "__main__":
    import sys
    print("\n".join(build_plugins(sys.argv[1], sys.argv[2])))
