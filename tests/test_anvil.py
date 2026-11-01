import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from mcsre.anvil import (ChunkCorrupt, Region, block_at, blocks_in_box, chunk_status, copy_chunk,
                         corrupt_chunk, entities_in_chunks, read_nbt)


class Long(int):
    pass


class Double(float):
    pass


def _str(s: str) -> bytes:
    b = s.encode()
    return struct.pack(">H", len(b)) + b


def _tag(v) -> int:
    if isinstance(v, bool) or isinstance(v, Long):
        return 4
    if isinstance(v, int):
        return 3
    if isinstance(v, float):
        return 6
    if isinstance(v, str):
        return 8
    if isinstance(v, dict):
        return 10
    if isinstance(v, tuple):
        return 12
    if isinstance(v, list):
        return 9
    raise TypeError(v)


def _payload(v) -> bytes:
    t = _tag(v)
    if t == 4:
        return struct.pack(">q", v)
    if t == 3:
        return struct.pack(">i", v)
    if t == 6:
        return struct.pack(">d", v)
    if t == 8:
        return _str(v)
    if t == 10:
        return b"".join(bytes([_tag(x)]) + _str(k) + _payload(x) for k, x in v.items()) + b"\0"
    if t == 12:
        return struct.pack(">i", len(v)) + b"".join(struct.pack(">q", x) for x in v)
    inner = _tag(v[0]) if v else 0
    return bytes([inner]) + struct.pack(">i", len(v)) + b"".join(_payload(x) for x in v)


def write_nbt(root: dict) -> bytes:
    return b"\x0a" + _str("") + _payload(root)


def pack_states(indices: list[int], bits: int) -> tuple:
    per_long = 64 // bits
    longs = []
    for start in range(0, len(indices), per_long):
        word = 0
        for j, v in enumerate(indices[start:start + per_long]):
            word |= v << (j * bits)
        longs.append(struct.unpack(">q", struct.pack(">Q", word))[0])
    return tuple(longs)


def section(y: int, blocks: dict[tuple[int, int, int], str], fill="minecraft:air") -> dict:
    palette = [fill] + sorted(set(blocks.values()) - {fill})
    if len(palette) == 1:
        return {"Y": y, "block_states": {"palette": [{"Name": fill}]}}
    bits = max(4, (len(palette) - 1).bit_length())
    indices = [0] * 4096
    for (x, yy, z), name in blocks.items():
        indices[(yy & 15) * 256 + (z & 15) * 16 + (x & 15)] = palette.index(name)
    return {"Y": y, "block_states": {"palette": [{"Name": n} for n in palette],
                                     "data": pack_states(indices, bits)}}


def record(root: dict) -> bytes:
    payload = zlib.compress(write_nbt(root))
    return struct.pack(">IB", len(payload) + 1, 2) + payload


class World:
    def __init__(self, base: Path):
        self.dir = base / "world"
        (self.dir / "region").mkdir(parents=True)
        (self.dir / "entities").mkdir()

    def region_path(self, rx, rz, kind="region") -> Path:
        return self.dir / kind / f"r.{rx}.{rz}.mca"

    def put(self, cx, cz, root, kind="region", timestamp=1000):
        path = self.region_path(cx >> 5, cz >> 5, kind)
        region = Region.load(path) if path.exists() else Region()
        region.records[(cx & 31, cz & 31)] = record(root)
        region.timestamps[(cx & 31, cz & 31)] = timestamp
        region.save(path)


def blocks_chunk(blocks: dict[tuple[int, int, int], str]) -> dict:
    by_section: dict[int, dict] = {}
    for pos, name in blocks.items():
        by_section.setdefault(pos[1] >> 4, {})[pos] = name
    by_section.setdefault(-4, None)
    sections = [section(y, b) if b else section(y, {}, fill="minecraft:bedrock")
                for y, b in sorted(by_section.items())]
    return {"DataVersion": 3700, "Status": "minecraft:full", "sections": sections}


class AnvilTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.world = World(Path(self.tmp.name))
        self.world.put(0, 0, blocks_chunk({(1, 5, 2): "minecraft:stone", (15, 70, 15): "minecraft:oak_planks",
                                           (3, 5, 3): "minecraft:glass"}), timestamp=111)
        self.world.put(-2, -2, blocks_chunk({(-20, -60, -20): "minecraft:gold_block"}), timestamp=222)
        self.world.put(-1, -2, blocks_chunk({(-10, -60, -20): "minecraft:diamond_block"}), timestamp=333)

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_nbt_all_tag_types(self):
        data = (b"\x0a" + _str("root")
                + b"\x01" + _str("b") + struct.pack(">b", -3)
                + b"\x02" + _str("s") + struct.pack(">h", -300)
                + b"\x05" + _str("f") + struct.pack(">f", 1.5)
                + b"\x07" + _str("ba") + struct.pack(">i", 2) + b"\x01\x02"
                + b"\x0b" + _str("ia") + struct.pack(">iii", 2, 1, -7)
                + b"\x09" + _str("empty") + b"\x00" + struct.pack(">i", 0)
                + b"\x00")
        name, value = read_nbt(data)
        self.assertEqual(name, "root")
        self.assertEqual(value, {"b": -3, "s": -300, "f": 1.5, "ba": b"\x01\x02", "ia": [1, -7], "empty": []})

    def test_block_at_reads_literal_names(self):
        w = self.world.dir
        self.assertEqual(block_at(w, 1, 5, 2), "minecraft:stone")
        self.assertEqual(block_at(w, 3, 5, 3), "minecraft:glass")
        self.assertEqual(block_at(w, 15, 70, 15), "minecraft:oak_planks")
        self.assertEqual(block_at(w, 2, 5, 2), "minecraft:air")
        self.assertEqual(block_at(w, 0, -64, 0), "minecraft:bedrock")
        self.assertEqual(block_at(w, -20, -60, -20), "minecraft:gold_block")
        self.assertEqual(block_at(w, 0, 200, 0), "minecraft:air")
        self.assertEqual(block_at(w, 500, 5, 500), "minecraft:air")

    def test_wide_palette_uses_more_bits(self):
        names = {(x, 0, z): f"minecraft:block_{x}_{z}" for x in range(5) for z in range(5)}
        self.world.put(1, 0, blocks_chunk({(16 + x, y, z): n for (x, y, z), n in names.items()}))
        self.assertEqual(block_at(self.world.dir, 19, 0, 2), "minecraft:block_3_2")
        self.assertEqual(block_at(self.world.dir, 21, 0, 0), "minecraft:air")

    def test_blocks_in_box_spans_chunks(self):
        got = blocks_in_box(self.world.dir, (-20, -60, -20), (-10, -60, -20))
        self.assertEqual(len(got), 11)
        self.assertEqual(got[(-20, -60, -20)], "minecraft:gold_block")
        self.assertEqual(got[(-10, -60, -20)], "minecraft:diamond_block")
        self.assertEqual(got[(-15, -60, -20)], "minecraft:air")

    def test_copy_chunk_moves_exactly_one_chunk(self):
        src_dir = Path(self.tmp.name) / "backup"
        src = World(src_dir)
        src.put(-2, -2, blocks_chunk({(-20, -60, -20): "minecraft:emerald_block"}), timestamp=999)
        src.put(-1, -2, blocks_chunk({(-10, -60, -20): "minecraft:emerald_block"}), timestamp=999)
        dst_path = self.world.region_path(-1, -1)
        copy_chunk(src.region_path(-1, -1), dst_path, -2, -2)
        self.assertEqual(block_at(self.world.dir, -20, -60, -20), "minecraft:emerald_block")
        self.assertEqual(block_at(self.world.dir, -10, -60, -20), "minecraft:diamond_block")
        self.assertEqual(Region.load(dst_path).timestamp(30, 30), 999)
        self.assertEqual(Region.load(dst_path).timestamp(31, 30), 333)
        with self.assertRaises(KeyError):
            copy_chunk(src.region_path(-1, -1), dst_path, -5, -5)

    def test_corrupt_chunk_breaks_only_that_chunk(self):
        path = self.world.region_path(-1, -1)
        before = Region.load(path).raw(30, 30)
        corrupt_chunk(path, -2, -2, seed=7)
        after = Region.load(path).raw(30, 30)
        self.assertEqual(after[:5], before[:5])
        self.assertNotEqual(after, before)
        status = {tuple(s["chunk"]): s for s in chunk_status(path)}
        self.assertEqual(status[(-2, -2)]["status"], "corrupt")
        self.assertIn("decompress", status[(-2, -2)]["reason"])
        self.assertEqual(status[(-1, -2)], {"chunk": [-1, -2], "status": "ok", "reason": None, "timestamp": 333})
        with self.assertRaises(ChunkCorrupt):
            block_at(self.world.dir, -20, -60, -20)
        self.assertEqual(block_at(self.world.dir, -10, -60, -20), "minecraft:diamond_block")

    def test_corrupt_chunk_is_deterministic(self):
        path = self.world.region_path(-1, -1)
        original = path.read_bytes()
        corrupt_chunk(path, -2, -2, seed=7)
        first = path.read_bytes()
        path.write_bytes(original)
        corrupt_chunk(path, -2, -2, seed=7)
        self.assertEqual(path.read_bytes(), first)

    def test_save_load_round_trip(self):
        path = self.world.region_path(0, 0)
        region = Region.load(path)
        copy = Path(self.tmp.name) / "r.0.0.mca"
        region.save(copy)
        again = Region.load(copy)
        self.assertEqual(again.chunks(), [(0, 0)])
        self.assertEqual(again.raw(0, 0), region.raw(0, 0))
        self.assertEqual(again.timestamp(0, 0), 111)
        self.assertEqual(again.nbt(0, 0), region.nbt(0, 0))
        data = copy.read_bytes()
        self.assertEqual(len(data) % 4096, 0)
        loc = struct.unpack_from(">I", data, 0)[0]
        self.assertEqual(loc >> 8, 2)
        self.assertEqual(loc & 0xFF, (len(data) - 8192) // 4096)

    def test_entities_in_chunks(self):
        pig = {"id": "minecraft:pig", "CustomName": '"Dolly"', "Pos": [Double(5.5), Double(-60.0), Double(5.5)]}
        cow = {"id": "minecraft:cow", "Pos": [Double(-3.0), Double(-60.0), Double(-3.0)]}
        self.world.put(0, 0, {"DataVersion": 3700, "Position": (0, 0), "Entities": [pig]}, kind="entities")
        self.world.put(-1, -1, {"DataVersion": 3700, "Entities": [cow]}, kind="entities")
        got = sorted(entities_in_chunks(self.world.dir), key=lambda e: e["id"])
        self.assertEqual(got, [
            {"id": "minecraft:cow", "custom_name": None, "pos": [-3.0, -60.0, -3.0]},
            {"id": "minecraft:pig", "custom_name": '"Dolly"', "pos": [5.5, -60.0, 5.5]},
        ])


if __name__ == "__main__":
    unittest.main()
