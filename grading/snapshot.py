"""World state snapshots for diff-based grading."""
import hashlib
import os
import time
from dataclasses import dataclass, field

from server.rcon import Rcon


@dataclass
class BlockRecord:
    x: int
    y: int
    z: int
    block_id: str


@dataclass
class WorldSnapshot:
    timestamp: float = 0.0
    region_hashes: dict = field(default_factory=dict)
    build_blocks: list = field(default_factory=list)
    entity_summary: dict = field(default_factory=dict)


def hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_region_files(world_dir: str) -> dict[str, str]:
    hashes = {}
    for subdir in ("region", "entities"):
        region_path = os.path.join(world_dir, subdir)
        if not os.path.isdir(region_path):
            continue
        for fname in sorted(os.listdir(region_path)):
            if fname.endswith(".mca"):
                fpath = os.path.join(region_path, fname)
                hashes[f"{subdir}/{fname}"] = hash_file(fpath)
    return hashes


def read_block(rcon: Rcon, x: int, y: int, z: int) -> str:
    resp = rcon.command(f"data get block {x} {y} {z}")
    if "has the following block data" in resp:
        if "id:" in resp:
            start = resp.index('id:') + 3
            end = resp.index(',', start) if ',' in resp[start:] else resp.index('}', start)
            return resp[start:end].strip().strip('"').strip("'")
    if "block data" in resp.lower():
        return resp
    return resp


def read_build_blocks(rcon: Rcon, coords: list[tuple[int, int, int]]) -> list[BlockRecord]:
    blocks = []
    for x, y, z in coords:
        try:
            block_id = read_block(rcon, x, y, z)
            blocks.append(BlockRecord(x, y, z, block_id))
        except Exception:
            blocks.append(BlockRecord(x, y, z, "ERROR"))
    return blocks


def take_snapshot(
    rcon: Rcon,
    world_dir: str,
    build_coords: list[tuple[int, int, int]],
) -> WorldSnapshot:
    rcon.command("save-all flush")
    time.sleep(2)

    snap = WorldSnapshot(timestamp=time.time())
    snap.region_hashes = hash_region_files(world_dir)
    snap.build_blocks = read_build_blocks(rcon, build_coords)

    return snap
