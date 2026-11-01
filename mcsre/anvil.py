"""Anvil region files (.mca) and NBT, read straight from disk, Minecraft 1.20.4 layout."""

import gzip
import os
import random
import re
import struct
import zlib
from pathlib import Path
from typing import Any

SECTOR = 4096
AIR = "minecraft:air"


class ChunkCorrupt(Exception):
    pass


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("NBT truncated")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def unpack(self, fmt: str):
        return struct.unpack(">" + fmt, self.take(struct.calcsize(">" + fmt)))[0]

    def string(self) -> str:
        return self.take(self.unpack("H")).decode("utf-8", "replace")

    def array(self, code: str) -> list[int]:
        n = self.unpack("i")
        return list(struct.unpack(f">{n}{code}", self.take(n * struct.calcsize(code))))

    def payload(self, tag: int) -> Any:
        if tag == 1:
            return self.unpack("b")
        if tag == 2:
            return self.unpack("h")
        if tag == 3:
            return self.unpack("i")
        if tag == 4:
            return self.unpack("q")
        if tag == 5:
            return self.unpack("f")
        if tag == 6:
            return self.unpack("d")
        if tag == 7:
            return self.take(self.unpack("i"))
        if tag == 8:
            return self.string()
        if tag == 9:
            inner = self.unpack("b")
            n = self.unpack("i")
            return [self.payload(inner) for _ in range(n)]
        if tag == 10:
            out = {}
            while True:
                t = self.unpack("b")
                if t == 0:
                    return out
                name = self.string()
                out[name] = self.payload(t)
        if tag == 11:
            return self.array("i")
        if tag == 12:
            return self.array("q")
        raise ValueError(f"unknown NBT tag {tag}")


def read_nbt(data: bytes) -> tuple[str, Any]:
    r = _Reader(data)
    tag = r.unpack("b")
    if tag == 0:
        return "", None
    name = r.string()
    return name, r.payload(tag)


class Region:
    def __init__(self, records: dict | None = None, timestamps: dict | None = None):
        self.records: dict[tuple[int, int], bytes] = records or {}
        self.timestamps: dict[tuple[int, int], int] = timestamps or {}

    @classmethod
    def load(cls, path) -> "Region":
        data = Path(path).read_bytes()
        region = cls()
        if len(data) < 2 * SECTOR:
            return region
        for i in range(1024):
            loc = struct.unpack_from(">I", data, i * 4)[0]
            offset, count = loc >> 8, loc & 0xFF
            if offset == 0 and count == 0:
                continue
            key = (i % 32, i // 32)
            start = offset * SECTOR
            record = data[start:start + count * SECTOR]
            if len(record) >= 5:
                length = struct.unpack_from(">I", record)[0]
                if 0 < length <= len(record) - 4:
                    record = record[:4 + length]
            region.records[key] = record
            region.timestamps[key] = struct.unpack_from(">I", data, SECTOR + i * 4)[0]
        return region

    def chunks(self) -> list[tuple[int, int]]:
        return sorted(self.records, key=lambda k: (k[1], k[0]))

    def timestamp(self, lx: int, lz: int) -> int:
        return self.timestamps.get((lx, lz), 0)

    def raw(self, lx: int, lz: int) -> bytes:
        return self.records[(lx, lz)]

    def nbt(self, lx: int, lz: int) -> dict:
        record = self.records.get((lx, lz))
        if record is None:
            raise KeyError((lx, lz))
        if len(record) < 5:
            raise ChunkCorrupt("record shorter than its 5-byte header")
        length, ctype = struct.unpack_from(">IB", record)
        if length == 0 or length > len(record) - 4:
            raise ChunkCorrupt(f"length {length} exceeds the {len(record) - 4} bytes on disk")
        payload = record[5:4 + length]
        try:
            if ctype == 2:
                raw = zlib.decompress(payload)
            elif ctype == 1:
                raw = gzip.decompress(payload)
            elif ctype == 3:
                raw = payload
            else:
                raise ChunkCorrupt(f"unsupported compression type {ctype}")
        except ChunkCorrupt:
            raise
        except Exception as e:
            raise ChunkCorrupt(f"decompress failed: {e}") from e
        try:
            _, root = read_nbt(raw)
        except Exception as e:
            raise ChunkCorrupt(f"NBT parse failed: {e}") from e
        if not isinstance(root, dict):
            raise ChunkCorrupt("root tag is not a compound")
        return root

    def save(self, path) -> None:
        header = bytearray(2 * SECTOR)
        body = bytearray()
        next_sector = 2
        for (lx, lz) in self.chunks():
            record = self.records[(lx, lz)]
            sectors = -(-len(record) // SECTOR)
            if sectors > 255:
                raise ValueError(f"chunk ({lx}, {lz}) needs {sectors} sectors; external .mcc not supported")
            i = lx + lz * 32
            struct.pack_into(">I", header, i * 4, (next_sector << 8) | sectors)
            struct.pack_into(">I", header, SECTOR + i * 4, self.timestamps.get((lx, lz), 0))
            body += record + b"\0" * (sectors * SECTOR - len(record))
            next_sector += sectors
        tmp = Path(str(path) + ".tmp")
        tmp.write_bytes(bytes(header) + bytes(body))
        os.replace(tmp, path)


_REGION_NAME = re.compile(r"r\.(-?\d+)\.(-?\d+)\.mca$")


def _region_coords(path) -> tuple[int, int]:
    m = _REGION_NAME.search(str(path))
    if not m:
        raise ValueError(f"not a region file name: {path}")
    return int(m.group(1)), int(m.group(2))


def chunk_status(region_path) -> list[dict]:
    rx, rz = _region_coords(region_path)
    region = Region.load(region_path)
    out = []
    for lx, lz in region.chunks():
        status, reason = "ok", None
        try:
            region.nbt(lx, lz)
        except ChunkCorrupt as e:
            status, reason = "corrupt", str(e)
        out.append({"chunk": [rx * 32 + lx, rz * 32 + lz], "status": status, "reason": reason,
                    "timestamp": region.timestamp(lx, lz)})
    return out


def copy_chunk(src_region_path, dst_region_path, cx: int, cz: int) -> None:
    key = (cx & 31, cz & 31)
    src = Region.load(src_region_path)
    if key not in src.records:
        raise KeyError(f"chunk ({cx}, {cz}) not present in {src_region_path}")
    dst = Region.load(dst_region_path) if Path(dst_region_path).exists() else Region()
    dst.records[key] = src.records[key]
    dst.timestamps[key] = src.timestamps.get(key, 0)
    dst.save(dst_region_path)


def corrupt_chunk(region_path, cx: int, cz: int, seed: int) -> None:
    key = (cx & 31, cz & 31)
    region = Region.load(region_path)
    record = region.records[key]
    rng = random.Random(seed)
    garbage = bytes(rng.getrandbits(8) for _ in range(len(record) - 5))
    if garbage[:1] == b"\x78":
        garbage = b"\x00" + garbage[1:]
    region.records[key] = record[:5] + garbage
    region.save(region_path)


def _section_block(section: dict, x: int, y: int, z: int) -> str:
    states = section.get("block_states") or {}
    palette = states.get("palette") or []
    if not palette:
        return AIR
    if len(palette) == 1:
        return palette[0].get("Name", AIR)
    data = states.get("data") or []
    bits = max(4, (len(palette) - 1).bit_length())
    per_long = 64 // bits
    index = (y & 15) * 256 + (z & 15) * 16 + (x & 15)
    word = index // per_long
    if word >= len(data):
        raise ChunkCorrupt(f"block_states data has {len(data)} longs, needs index {word}")
    value = (data[word] >> ((index % per_long) * bits)) & ((1 << bits) - 1)
    if value >= len(palette):
        raise ChunkCorrupt(f"palette index {value} out of range {len(palette)}")
    return palette[value].get("Name", AIR)


class _World:
    def __init__(self, world_dir):
        self.region_dir = Path(world_dir) / "region"
        self.regions: dict[tuple[int, int], Region | None] = {}
        self.sections: dict[tuple[int, int], dict[int, dict] | None] = {}

    def _chunk_sections(self, cx: int, cz: int) -> dict[int, dict] | None:
        if (cx, cz) in self.sections:
            return self.sections[(cx, cz)]
        rkey = (cx >> 5, cz >> 5)
        if rkey not in self.regions:
            path = self.region_dir / f"r.{rkey[0]}.{rkey[1]}.mca"
            self.regions[rkey] = Region.load(path) if path.exists() else None
        region = self.regions[rkey]
        sections = None
        if region is not None and (cx & 31, cz & 31) in region.records:
            root = region.nbt(cx & 31, cz & 31)
            sections = {s.get("Y"): s for s in root.get("sections", [])}
        self.sections[(cx, cz)] = sections
        return sections

    def block(self, x: int, y: int, z: int) -> str:
        sections = self._chunk_sections(x >> 4, z >> 4)
        if sections is None:
            return AIR
        section = sections.get(y >> 4)
        if section is None:
            return AIR
        return _section_block(section, x, y, z)


def block_at(world_dir, x: int, y: int, z: int) -> str:
    return _World(world_dir).block(x, y, z)


def blocks_in_box(world_dir, a: tuple[int, int, int], b: tuple[int, int, int]) -> dict[tuple[int, int, int], str]:
    world = _World(world_dir)
    (x1, x2), (y1, y2), (z1, z2) = (sorted((a[i], b[i])) for i in range(3))
    return {(x, y, z): world.block(x, y, z)
            for x in range(x1, x2 + 1) for y in range(y1, y2 + 1) for z in range(z1, z2 + 1)}


def entities_in_chunks(world_dir) -> list[dict]:
    out = []
    for path in sorted((Path(world_dir) / "entities").glob("r.*.*.mca")):
        region = Region.load(path)
        for lx, lz in region.chunks():
            root = region.nbt(lx, lz)
            for e in root.get("Entities", []):
                out.append({"id": e.get("id"), "custom_name": e.get("CustomName"),
                            "pos": list(e.get("Pos", []))})
    return out
