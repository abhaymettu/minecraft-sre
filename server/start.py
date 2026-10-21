"""Start and manage the Minecraft server process."""
import os
import signal
import subprocess
import sys
import time

from .setup import SERVER_DIR, JAR_NAME, setup

CONSERVATIVE_FLAGS = [
    "-Xms256M",
    "-Xmx512M",
    "-XX:+UseSerialGC",
    "-Xlog:gc*:file=gc.log:time,uptime,level,tags",
]

TUNED_FLAGS = [
    "-Xms512M",
    "-Xmx1G",
    "-XX:+UseG1GC",
    "-XX:+ParallelRefProcEnabled",
    "-XX:MaxGCPauseMillis=200",
    "-XX:G1HeapRegionSize=8M",
    "-XX:G1NewSizePercent=30",
    "-XX:G1MaxNewSizePercent=40",
    "-XX:G1MixedGCCountTarget=4",
    "-Xlog:gc*:file=gc.log:time,uptime,level,tags",
]


class MinecraftServer:
    def __init__(self, server_dir=None, jvm_flags=None):
        self.server_dir = server_dir or SERVER_DIR
        self.jvm_flags = jvm_flags or CONSERVATIVE_FLAGS
        self.proc = None

    def start(self, wait_ready=True, timeout=120):
        setup(self.server_dir)
        jar_path = os.path.join(self.server_dir, JAR_NAME)
        cmd = ["java"] + self.jvm_flags + ["-jar", jar_path, "--nogui"]

        self.proc = subprocess.Popen(
            cmd,
            cwd=self.server_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        if wait_ready:
            deadline = time.time() + timeout
            for line in self.proc.stdout:
                sys.stderr.write(f"[server] {line}")
                if "Done" in line and "help" in line.lower():
                    break
                if time.time() > deadline:
                    self.stop()
                    raise TimeoutError("server did not start within timeout")

        return self

    def stop(self, timeout=30):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
        self.proc = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def gc_log_path(self):
        return os.path.join(self.server_dir, "gc.log")

    @property
    def world_dir(self):
        return os.path.join(self.server_dir, "world")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


if __name__ == "__main__":
    with MinecraftServer() as srv:
        print("server running, press ctrl-c to stop")
        try:
            srv.proc.wait()
        except KeyboardInterrupt:
            pass
