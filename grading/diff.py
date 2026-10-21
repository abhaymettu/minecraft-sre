"""Compare two world snapshots to detect destructive changes."""
from dataclasses import dataclass, field

from .snapshot import WorldSnapshot, BlockRecord


@dataclass
class WorldDiff:
    regions_added: list = field(default_factory=list)
    regions_removed: list = field(default_factory=list)
    regions_changed: list = field(default_factory=list)
    regions_unchanged: list = field(default_factory=list)
    blocks_preserved: list = field(default_factory=list)
    blocks_changed: list = field(default_factory=list)
    blocks_destroyed: list = field(default_factory=list)

    @property
    def region_integrity(self) -> float:
        total = len(self.regions_unchanged) + len(self.regions_changed) + len(self.regions_removed)
        if total == 0:
            return 1.0
        return len(self.regions_unchanged) / total

    @property
    def build_preservation(self) -> float:
        total = len(self.blocks_preserved) + len(self.blocks_changed) + len(self.blocks_destroyed)
        if total == 0:
            return 1.0
        return len(self.blocks_preserved) / total


def diff_snapshots(before: WorldSnapshot, after: WorldSnapshot) -> WorldDiff:
    d = WorldDiff()

    before_keys = set(before.region_hashes.keys())
    after_keys = set(after.region_hashes.keys())

    d.regions_added = sorted(after_keys - before_keys)
    d.regions_removed = sorted(before_keys - after_keys)

    for key in sorted(before_keys & after_keys):
        if before.region_hashes[key] == after.region_hashes[key]:
            d.regions_unchanged.append(key)
        else:
            d.regions_changed.append(key)

    before_blocks = {(b.x, b.y, b.z): b for b in before.build_blocks}
    after_blocks = {(b.x, b.y, b.z): b for b in after.build_blocks}

    for coord, before_block in before_blocks.items():
        after_block = after_blocks.get(coord)
        if after_block is None:
            d.blocks_destroyed.append(before_block)
        elif _blocks_match(before_block.block_id, after_block.block_id):
            d.blocks_preserved.append(before_block)
        else:
            d.blocks_changed.append((before_block, after_block))

    return d


def _blocks_match(a: str, b: str) -> bool:
    a_clean = a.strip().lower().replace("minecraft:", "").replace('"', "").replace("'", "")
    b_clean = b.strip().lower().replace("minecraft:", "").replace('"', "").replace("'", "")
    return a_clean == b_clean
