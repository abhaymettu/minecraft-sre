"""Download and configure a Paper MC server."""
import json
import os
import hashlib
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(PROJECT_ROOT, ".server")
JAR_NAME = "paper.jar"
MC_VERSION = "1.20.4"

PROPERTIES = """\
server-port=25565
online-mode=false
enable-rcon=true
rcon.password=minecraft-sre
rcon.port=25575
level-type=flat
spawn-monsters=false
spawn-animals=false
difficulty=peaceful
max-players=20
view-distance=6
simulation-distance=6
generate-structures=false
motd=minecraft-sre scenario server
"""


def latest_paper_build():
    url = f"https://fill.papermc.io/v3/projects/paper/versions/{MC_VERSION}/builds"
    with urllib.request.urlopen(url, timeout=30) as resp:
        builds = json.loads(resp.read())
    stable = [b for b in builds if b.get("channel") == "STABLE"] or builds
    return max(b["id"] for b in stable)


def download_jar(dest):
    build = latest_paper_build()
    url = f"https://fill.papermc.io/v3/projects/paper/versions/{MC_VERSION}/builds/{build}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        info = json.loads(resp.read())["downloads"]["server:default"]
    print(f"downloading Paper {MC_VERSION} build {build}...")
    urllib.request.urlretrieve(info["url"], dest)
    want = info["checksums"]["sha256"]
    got = hashlib.sha256(open(dest, "rb").read()).hexdigest()
    if got != want:
        os.remove(dest)
        raise RuntimeError(f"paper.jar checksum mismatch: {got} != {want}")
    print(f"saved to {dest}")

def setup(server_dir=None):
    sdir = server_dir or SERVER_DIR
    os.makedirs(sdir, exist_ok=True)
    jar_path = os.path.join(sdir, JAR_NAME)
    if not os.path.exists(jar_path):
        download_jar(jar_path)

    with open(os.path.join(sdir, "eula.txt"), "w") as f:
        f.write("eula=true\n")

    with open(os.path.join(sdir, "server.properties"), "w") as f:
        f.write(PROPERTIES)

    return sdir


if __name__ == "__main__":
    setup()
