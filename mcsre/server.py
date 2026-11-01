"""Paper server download, per-episode server directories and process lifecycle."""
import hashlib
import json
import os
import shutil
import subprocess
import time
import urllib.request

from .rcon import Rcon, RconError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.join(ROOT, ".server")
CACHE_DIR = os.path.join(ROOT, ".cache")
TEMPLATE_DIR = os.path.join(CACHE_DIR, "template")
PLUGIN_JARS = os.path.join(CACHE_DIR, "plugins")
MC_VERSION = "1.20.4"
RCON_PASSWORD = "minecraft-sre"
UA = {"User-Agent": "minecraft-sre/1.0 (github.com/abhaymettu/minecraft-sre)"}
SHARED = ("paper.jar", "libraries", "versions", "cache")

JVM_FLAGS = ["-Xms256M", "-Xmx768M", "-XX:+UseG1GC", "-XX:+ExitOnOutOfMemoryError"]


def properties(port, rcon_port, **overrides):
    props = {
        "server-ip": "127.0.0.1",
        "server-port": port,
        "enable-rcon": "true",
        "rcon.port": rcon_port,
        "rcon.password": RCON_PASSWORD,
        "online-mode": "false",
        "level-type": "minecraft\\:flat",
        "generate-structures": "false",
        "spawn-monsters": "false",
        "spawn-animals": "true",
        "spawn-npcs": "true",
        "difficulty": "peaceful",
        "spawn-protection": "0",
        "max-players": "20",
        "view-distance": "6",
        "simulation-distance": "6",
        "white-list": "false",
        "enforce-whitelist": "false",
        "motd": "Maple Town",
        "enable-query": "false",
    }
    props.update(overrides)
    return "".join(f"{k}={v}\n" for k, v in props.items())


def read_properties(path):
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def ensure_paper_jar():
    os.makedirs(BASE_DIR, exist_ok=True)
    jar = os.path.join(BASE_DIR, "paper.jar")
    if os.path.exists(jar):
        return jar
    api = f"https://fill.papermc.io/v3/projects/paper/versions/{MC_VERSION}/builds"
    with urllib.request.urlopen(urllib.request.Request(api, headers=UA), timeout=30) as r:
        builds = json.loads(r.read())
    stable = [b for b in builds if b.get("channel") == "STABLE"] or builds
    info = max(stable, key=lambda b: b["id"])["downloads"]["server:default"]
    print(f"downloading Paper {MC_VERSION} ({info['url'].rsplit('/', 1)[-1]})")
    with urllib.request.urlopen(urllib.request.Request(info["url"], headers=UA), timeout=300) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != info["checksums"]["sha256"]:
        raise RuntimeError("paper.jar checksum mismatch")
    with open(jar + ".part", "wb") as f:
        f.write(data)
    os.replace(jar + ".part", jar)
    return jar


def link_shared(server_dir):
    for name in ("libraries", "versions", "cache"):
        os.makedirs(os.path.join(BASE_DIR, name), exist_ok=True)
    for name in SHARED:
        dst = os.path.join(server_dir, name)
        if not os.path.lexists(dst):
            os.symlink(os.path.join(BASE_DIR, name), dst)


def copy_server(src, dst):
    """Copy a server dir, recreating the shared symlinks instead of copying them."""
    shutil.copytree(src, dst, symlinks=True, ignore=lambda d, names: [n for n in names if d == src and n in SHARED])
    link_shared(dst)


class Server:
    def __init__(self, server_dir, port, rcon_port, jvm_flags=None):
        self.dir = server_dir
        self.port = port
        self.rcon_port = rcon_port
        self.jvm_flags = jvm_flags or JVM_FLAGS
        self.proc = None
        self._console = None

    def rcon(self, timeout=10):
        return Rcon(port=self.rcon_port, password=RCON_PASSWORD, timeout=timeout)

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, timeout=300):
        if self.running:
            return
        link_shared(self.dir)
        self._console = open(os.path.join(self.dir, "console.out"), "ab")
        self.proc = subprocess.Popen(
            ["java", *self.jvm_flags, "-jar", "paper.jar", "--nogui"],
            cwd=self.dir, stdin=subprocess.DEVNULL, stdout=self._console, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        probe = self.rcon(timeout=3)
        while time.time() < deadline:
            if not self.running:
                raise RuntimeError(f"server exited during startup (code {self.proc.returncode}), see {self.dir}/console.out")
            try:
                probe.connect()
                probe.command("list", retry=False)
                probe.close()
                return
            except (OSError, RconError):
                time.sleep(1)
        self.kill()
        raise TimeoutError("server did not open RCON in time")

    def stop(self, timeout=60):
        if not self.running:
            self.proc = None
            return
        try:
            r = self.rcon(timeout=5)
            r.command("stop", retry=False)
            r.close()
        except (OSError, RconError):
            self.proc.terminate()
        try:
            self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.kill()
        self.proc = None

    def kill(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(10)
        self.proc = None

    def restart(self):
        self.stop()
        self.start()
