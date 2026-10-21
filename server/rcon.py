"""Minecraft RCON protocol client."""
import re
import struct
import socket
import time


class RconError(Exception):
    pass


COLOR_RE = re.compile(r"§[0-9a-fk-or]")


def strip_color(text):
    return COLOR_RE.sub("", text)


class Rcon:
    def __init__(self, host="127.0.0.1", port=25575, password="minecraft-sre"):
        self.host = host
        self.port = port
        self.password = password
        self._sock = None
        self._req_id = 0

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(10)
        self._sock.connect((self.host, self.port))
        resp = self._send(3, self.password)
        if resp["id"] == -1:
            raise RconError("authentication failed")

    def command(self, cmd):
        if not self._sock:
            raise RconError("not connected")
        resp = self._send(2, cmd)
        return strip_color(resp["payload"])

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None

    def ping(self):
        try:
            self.command("list")
            return True
        except (OSError, RconError):
            return False

    def wait_ready(self, timeout=120, interval=2):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self.connect()
                if self.ping():
                    return True
            except (OSError, RconError):
                pass
            time.sleep(interval)
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
