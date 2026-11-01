package sre.blocklog;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class BlockLog extends JavaPlugin implements Listener {
    private BufferedWriter out;

    @Override
    public void onEnable() {
        getDataFolder().mkdirs();
        File csv = new File(getDataFolder(), "blocks.csv");
        boolean fresh = !csv.exists() || csv.length() == 0;
        try {
            out = new BufferedWriter(new FileWriter(csv, StandardCharsets.UTF_8, true));
            if (fresh) {
                out.write("time,player,action,world,x,y,z,before,after\n");
                out.flush();
            }
        } catch (IOException e) {
            throw new IllegalStateException("cannot open blocks.csv", e);
        }
        getServer().getPluginManager().registerEvents(this, this);
    }

    @Override
    public void onDisable() {
        try {
            if (out != null) out.close();
        } catch (IOException ignored) {
        }
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onBreak(BlockBreakEvent e) {
        log(e.getPlayer().getName(), "break", e.getBlock().getLocation(), e.getBlock().getType(), Material.AIR);
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onPlace(BlockPlaceEvent e) {
        log(e.getPlayer().getName(), "place", e.getBlockPlaced().getLocation(),
            e.getBlockReplacedState().getType(), e.getBlockPlaced().getType());
    }

    private void log(String player, String action, Location loc, Material before, Material after) {
        String line = Instant.now() + "," + player + "," + action + "," + loc.getWorld().getName() + ","
            + loc.getBlockX() + "," + loc.getBlockY() + "," + loc.getBlockZ() + ","
            + before.getKey() + "," + after.getKey() + "\n";
        try {
            out.write(line);
            out.flush();
        } catch (IOException e) {
            getLogger().warning("could not write blocks.csv: " + e);
        }
    }
}
