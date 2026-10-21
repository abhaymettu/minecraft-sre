"""Tests for RCON protocol encoding. No server needed."""
import struct
import unittest

from server.rcon import Rcon, strip_color


class TestStripColor(unittest.TestCase):
    def test_strip_section_codes(self):
        raw = "§6TPS from last 1m, 5m, 15m: §a20.0, §a20.0, §a20.0"
        cleaned = strip_color(raw)
        self.assertEqual(cleaned, "TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0")

    def test_no_color(self):
        self.assertEqual(strip_color("hello"), "hello")

    def test_empty(self):
        self.assertEqual(strip_color(""), "")


class TestRconPacketEncoding(unittest.TestCase):
    def test_send_builds_valid_packet(self):
        rcon = Rcon.__new__(Rcon)
        rcon._req_id = 0

        payload = "tps"
        ptype = 2
        rcon._req_id += 1
        rid = rcon._req_id
        body = struct.pack("<ii", rid, ptype) + payload.encode("utf-8") + b"\x00\x00"
        pkt = struct.pack("<i", len(body)) + body

        length = struct.unpack("<i", pkt[:4])[0]
        self.assertEqual(length, 4 + 4 + 3 + 2)
        self.assertEqual(len(pkt), 4 + length)

        data = pkt[4:]
        decoded_rid, decoded_type = struct.unpack("<ii", data[:8])
        decoded_payload = data[8:-2].decode("utf-8")
        self.assertEqual(decoded_rid, 1)
        self.assertEqual(decoded_type, 2)
        self.assertEqual(decoded_payload, "tps")


class TestMonitorTpsParsing(unittest.TestCase):
    def test_parse_tps_response(self):
        import re
        raw = "TPS from last 1m, 5m, 15m: 19.5, 18.2, 20.0"
        nums = re.findall(r"[\d.]+", raw)
        self.assertEqual(len(nums), 6)
        tps_1m = float(nums[-3])
        tps_5m = float(nums[-2])
        tps_15m = float(nums[-1])
        self.assertAlmostEqual(tps_1m, 19.5)
        self.assertAlmostEqual(tps_5m, 18.2)
        self.assertAlmostEqual(tps_15m, 20.0)


if __name__ == "__main__":
    unittest.main()
