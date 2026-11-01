"""Minecraft RCON protocol client."""
import re
import socket
import struct
import threading


class RconError(Exception):
    pass


COLOR_RE = re.compile(r"§[0-9a-fk-or]")


def strip_color(text):
    return COLOR_RE.sub("", text)


class Rcon:
    def __init__(self, host="127.0.0.1", port=25575, password="minecraft-sre", timeout=10):
        self.host = host
        self.timeout = timeout
        self.port = port
        self.password = password
        self._sock = None
        self._req_id = 0
        self._lock = threading.Lock()

    def connect(self):
        with self._lock:
            self._connect_locked()

    def _connect_locked(self):
        self._close_locked()
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        resp = self._send(3, self.password)
        if resp["id"] == -1:
            self._close_locked()
            raise RconError("authentication failed")

    def command(self, cmd, retry=True):
        with self._lock:
            try:
                if not self._sock:
                    self._connect_locked()
                return strip_color(self._send(2, cmd)["payload"])
            except (OSError, RconError):
                self._close_locked()
                if not retry:
                    raise
            self._connect_locked()
            return strip_color(self._send(2, cmd)["payload"])

    def close(self):
        with self._lock:
            self._close_locked()

    def _close_locked(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def ping(self):
        try:
            self.command("list", retry=False)
            return True
        except (OSError, RconError):
            return False

    def _send(self, ptype, payload):
        self._req_id += 1
        rid = self._req_id
        body = struct.pack("<ii", rid, ptype) + payload.encode("utf-8") + b"\x00\x00"
        pkt = struct.pack("<i", len(body)) + body
        self._sock.sendall(pkt)
        return self._recv()

    def _recv(self):
        raw_len = self._recvall(4)
        length = struct.unpack("<i", raw_len)[0]
        data = self._recvall(length)
        rid, ptype = struct.unpack("<ii", data[:8])
        payload = data[8:-2].decode("utf-8", errors="replace")
        return {"id": rid, "type": ptype, "payload": payload}

    def _recvall(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise RconError("connection closed")
            buf += chunk
        return buf

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()
