"""Render a recorded episode (MCSRE_RECORD=1) to a GIF: isometric world view, the agent's tool calls and MSPT."""
import json
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 675
BG, PANEL, INK, DIM, ACCENT, RED, GREEN = (14, 17, 22), (22, 27, 34), (230, 237, 243), (125, 133, 144), (88, 166, 255), (248, 81, 73), (63, 185, 80)
COLORS = {
    "grass_block": (95, 159, 53), "dirt": (134, 96, 67), "cobblestone": (122, 122, 122), "oak_planks": (162, 130, 78),
    "spruce_planks": (114, 84, 48), "stone_bricks": (122, 121, 122), "polished_andesite": (132, 134, 133),
    "glass": (190, 220, 230), "glass_pane": (190, 220, 230), "gold_block": (246, 208, 61), "bricks": (150, 97, 83),
    "dark_oak_planks": (66, 43, 20), "deepslate_bricks": (70, 70, 71), "bookshelf": (117, 94, 59),
    "crafting_table": (130, 96, 58), "chest": (163, 115, 48), "netherrack": (110, 50, 50), "bedrock": (60, 60, 60),
}
TILE = 9


def font(size):
    for p in ("/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def draw_world(d, frame, ox, oy):
    pal = [p.replace("minecraft:", "") for p in frame["palette"]]
    solid = {(x, y, z): pal[i] for x, y, z, i in frame["cells"]}
    for (x, y, z) in sorted(solid, key=lambda p: (p[0] + p[2], p[1], p[0])):
        c = COLORS.get(solid[(x, y, z)], (150, 150, 150))
        sx = ox + (x - z) * TILE
        sy = oy + (x + z) * TILE // 2 - y * TILE
        top = [(sx, sy - TILE // 2), (sx + TILE, sy), (sx, sy + TILE // 2), (sx - TILE, sy)]
        if (x, y + 1, z) not in solid:
            d.polygon(top, fill=c)
        if (x + 1, y, z) not in solid:
            d.polygon([(sx, sy + TILE // 2), (sx + TILE, sy), (sx + TILE, sy + TILE), (sx, sy + TILE + TILE // 2)], fill=shade(c, 0.78))
        if (x, y, z + 1) not in solid:
            d.polygon([(sx - TILE, sy), (sx, sy + TILE // 2), (sx, sy + TILE + TILE // 2), (sx - TILE, sy + TILE)], fill=shade(c, 0.6))


def tool_lines(audit, t0):
    out = []
    for a in audit:
        args = a["args"]
        if a["tool"] in ("status", "wait"):
            brief = f"wait {args.get('seconds')}s" if a["tool"] == "wait" else "status"
        elif a["tool"] == "console":
            brief = f"console  {args.get('command', '')}"
        elif a["tool"] in ("logs",):
            brief = f"logs  {args.get('grep') or args.get('path', '')}"
        elif a["tool"] == "mca":
            brief = f"mca {args.get('action')}  {args.get('region', '').split('/')[-1]}" + (
                f" chunk {args.get('chunk_x')},{args.get('chunk_z')}" if args.get("chunk_x") is not None else "")
        elif a["tool"] == "submit_report":
            brief = f"submit_report  resolved={args.get('resolved')}"
        elif a["tool"] == "declare_incident":
            brief = "declare_incident"
        else:
            brief = f"{a['tool']}  {args.get('path') or args.get('action') or ''}"
        out.append((a["t"] - t0, brief, a["error"]))
    return out


def render(ep_dir, gif_path=None):
    frames = [json.loads(l) for l in open(os.path.join(ep_dir, "frames.jsonl"))]
    tl = json.load(open(os.path.join(ep_dir, "timeline.json")))
    res = json.load(open(os.path.join(ep_dir, "result.json")))
    audit = [json.loads(l) for l in open(os.path.join(ep_dir, "audit.jsonl"))]
    calls = tool_lines(audit, tl["t0"])
    samples = tl["samples"]
    inject_t = tl["inject_t"]
    marks = {e["kind"]: e["t"] for e in tl["events"]}
    f_title, f_body, f_small = font(20), font(14), font(12)
    end_t = samples[-1]["t"] if samples else 1
    max_mspt = max([s["mspt"] or 0 for s in samples] + [60])
    images = []
    for fr in frames:
        t = fr["t"]
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        d.text((24, 16), "minecraft-sre", fill=INK, font=f_title)
        d.text((190, 20), f"{res['incident']}  ·  {res['agent']}", fill=DIM, font=f_body)
        d.text((W - 150, 20), f"t = {t:5.0f} s", fill=INK, font=f_body)
        d.rounded_rectangle((16, 56, 700, 500), 10, fill=PANEL)
        draw_world(d, fr, 140, 120)
        state = "incident active" if inject_t is not None and t >= inject_t else "normal"
        fixed = [s for s in samples if s["t"] <= t and s["fixed"] is not None]
        if fixed and fixed[-1]["fixed"]:
            state = "fixed"
        d.text((32, 470), state, fill={"normal": DIM, "incident active": RED, "fixed": GREEN}[state], font=f_body)
        d.rounded_rectangle((716, 56, W - 16, 500), 10, fill=PANEL)
        d.text((732, 66), "agent tool calls", fill=DIM, font=f_small)
        shown = [c for c in calls if c[0] <= t][-24:]
        for i, (ct, brief, err) in enumerate(shown):
            d.text((732, 88 + i * 17), f"{ct:4.0f}s  {brief[:52]}", fill=RED if err else (ACCENT if "console" in brief or "mca" in brief else INK), font=f_small)
        d.rounded_rectangle((16, 516, W - 16, H - 16), 10, fill=PANEL)
        d.text((32, 524), "mspt (lower is better, 50 = lag)", fill=DIM, font=f_small)
        x0, x1, y0, y1 = 32, W - 32, 548, H - 28
        pts = [(x0 + (x1 - x0) * s["t"] / end_t, y1 - (y1 - y0) * min(s["mspt"] or 0, max_mspt) / max_mspt) for s in samples if s["t"] <= t and s["mspt"] is not None]
        if len(pts) > 1:
            d.line(pts, fill=ACCENT, width=2)
        for kind, color in (("inject", RED), ("declare", (210, 153, 34)), ("report", GREEN)):
            if kind in marks and marks[kind] <= t:
                mx = x0 + (x1 - x0) * marks[kind] / end_t
                d.line([(mx, y0), (mx, y1)], fill=color, width=1)
                d.text((mx + 4, y0), kind, fill=color, font=f_small)
        images.append(im)
    gif_path = gif_path or os.path.join(ep_dir, "replay.gif")
    images[0].save(gif_path, save_all=True, append_images=images[1:], duration=400, loop=0, optimize=True)
    return gif_path
