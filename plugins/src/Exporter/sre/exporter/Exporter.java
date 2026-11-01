package sre.exporter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.TreeMap;

import org.bukkit.Bukkit;
import org.bukkit.World;
import org.bukkit.entity.Entity;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;
import org.bukkit.plugin.java.JavaPlugin;

public final class Exporter extends JavaPlugin {
    @Override
    public void onEnable() {
        getDataFolder().mkdirs();
        Bukkit.getScheduler().runTaskTimer(this, this::export, 20L, 20L);
    }

    private void export() {
        StringBuilder sb = new StringBuilder(1024);
        sb.append("{\"ts\":").append(System.currentTimeMillis());

        double[] tps = Bukkit.getTPS();
        sb.append(",\"tps\":[");
        for (int i = 0; i < 3; i++) {
            if (i > 0) sb.append(',');
            sb.append(round2(Math.min(20.0, tps[i])));
        }
        sb.append("],\"mspt\":").append(round2(Bukkit.getAverageTickTime()));

        Runtime rt = Runtime.getRuntime();
        sb.append(",\"heap_used_mb\":").append(round2((rt.totalMemory() - rt.freeMemory()) / 1048576.0));
        sb.append(",\"heap_max_mb\":").append(round2(rt.maxMemory() / 1048576.0));

        sb.append(",\"players\":[");
        boolean first = true;
        for (Player p : Bukkit.getOnlinePlayers()) {
            if (!first) sb.append(',');
            first = false;
            str(sb, p.getName());
        }
        sb.append(']');

        Map<String, Integer> byType = new TreeMap<>();
        int entities = 0;
        int chunks = 0;
        for (World w : Bukkit.getWorlds()) {
            chunks += w.getLoadedChunks().length;
            for (Entity e : w.getEntities()) {
                entities++;
                byType.merge(e.getType().getKey().toString(), 1, Integer::sum);
            }
        }
        sb.append(",\"entities\":").append(entities);
        sb.append(",\"entities_by_type\":{");
        first = true;
        for (Map.Entry<String, Integer> en : byType.entrySet()) {
            if (!first) sb.append(',');
            first = false;
            str(sb, en.getKey());
            sb.append(':').append(en.getValue());
        }
        sb.append("},\"chunks_loaded\":").append(chunks);

        sb.append(",\"plugins\":{");
        first = true;
        for (Plugin pl : Bukkit.getPluginManager().getPlugins()) {
            if (!first) sb.append(',');
            first = false;
            str(sb, pl.getName());
            sb.append(':').append(pl.isEnabled());
        }
        sb.append("}}\n");

        Path dir = getDataFolder().toPath();
        Path tmp = dir.resolve("metrics.json.tmp");
        try {
            Files.writeString(tmp, sb, StandardCharsets.UTF_8);
            Files.move(tmp, dir.resolve("metrics.json"), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            getLogger().warning("could not write metrics.json: " + e);
        }
    }

    private static double round2(double v) {
        return Math.round(v * 100.0) / 100.0;
    }

    private static void str(StringBuilder sb, String s) {
        sb.append('"');
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '"' || c == '\\') sb.append('\\').append(c);
            else if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
            else sb.append(c);
        }
        sb.append('"');
    }
}
