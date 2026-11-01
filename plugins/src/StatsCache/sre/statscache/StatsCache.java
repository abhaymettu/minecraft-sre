package sre.statscache;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.plugin.java.JavaPlugin;

public final class StatsCache extends JavaPlugin {
    private static final int ENTRY_BYTES = 300_000;
    private static final List<byte[]> HISTORY = new ArrayList<>();

    private long configMtime;
    private boolean retain;
    private int maxOnlineSeen;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        reload();
        getServer().getScheduler().runTaskTimer(this, this::tick, 1L, 1L);
        getServer().getScheduler().runTaskTimer(this, this::writeStats, 200L, 200L);
        getServer().getScheduler().runTaskTimer(this, () -> {
            if (configFile().lastModified() != configMtime) reload();
        }, 40L, 40L);
    }

    private File configFile() {
        return new File(getDataFolder(), "config.yml");
    }

    private void reload() {
        configMtime = configFile().lastModified();
        reloadConfig();
        retain = getConfig().getBoolean("retain-history", false);
        getLogger().info("StatsCache config reloaded (retain-history=" + retain + ")");
    }

    private void tick() {
        maxOnlineSeen = Math.max(maxOnlineSeen, getServer().getOnlinePlayers().size());
        if (!retain) return;
        byte[] snapshot = new byte[ENTRY_BYTES];
        Arrays.fill(snapshot, (byte) (HISTORY.size() | 1));
        HISTORY.add(snapshot);
    }

    private void writeStats() {
        String json = "{\"ts\":" + System.currentTimeMillis() + ",\"online\":" + getServer().getOnlinePlayers().size()
            + ",\"max_online_seen\":" + maxOnlineSeen + "}\n";
        Path dir = getDataFolder().toPath();
        Path tmp = dir.resolve("stats.json.tmp");
        try {
            Files.writeString(tmp, json);
            Files.move(tmp, dir.resolve("stats.json"), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException e) {
            getLogger().warning("could not write stats.json: " + e);
        }
    }

    private static String mb(int entries) {
        return String.format("%.1f MB", entries * (double) ENTRY_BYTES / 1048576.0);
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length != 1) return false;
        switch (args[0].toLowerCase()) {
            case "stats":
                sender.sendMessage("StatsCache history: " + HISTORY.size() + " entries, ~" + mb(HISTORY.size())
                    + " held (retain-history=" + retain + ")");
                return true;
            case "flush":
                int n = HISTORY.size();
                HISTORY.clear();
                System.gc();
                sender.sendMessage("StatsCache flushed " + n + " entries, freed ~" + mb(n));
                return true;
            default:
                return false;
        }
    }
}
