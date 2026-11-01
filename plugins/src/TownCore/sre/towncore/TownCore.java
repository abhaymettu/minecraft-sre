package sre.towncore;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.util.logging.Level;

import org.bukkit.configuration.InvalidConfigurationException;
import org.bukkit.configuration.file.FileConfiguration;
import org.bukkit.configuration.file.YamlConfiguration;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.plugin.java.JavaPlugin;

public final class TownCore extends JavaPlugin implements Listener {
    private long configMtime;
    private YamlConfiguration config = new YamlConfiguration();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        if (!loadAndValidate()) return;
        getServer().getPluginManager().registerEvents(this, this);
        getServer().getScheduler().runTaskTimer(this, this::tick, 40L, 40L);
    }

    private boolean loadAndValidate() {
        File file = new File(getDataFolder(), "config.yml");
        configMtime = file.lastModified();
        try {
            YamlConfiguration loaded = new YamlConfiguration();
            try {
                loaded.load(file);
            } catch (IOException | InvalidConfigurationException e) {
                throw new IllegalArgumentException("config.yml could not be parsed: " + e.getMessage(), e);
            }
            validate(loaded);
            config = loaded;
            return true;
        } catch (IllegalArgumentException e) {
            getLogger().log(Level.SEVERE, "TownCore failed to load config.yml, disabling", e);
            getServer().getPluginManager().disablePlugin(this);
            return false;
        }
    }

    static void validate(FileConfiguration c) {
        if (!c.isInt("economy.starting-balance")) {
            throw new IllegalArgumentException("economy.starting-balance must be an integer, got: "
                + describe(c.get("economy.starting-balance")));
        }
        Object tax = c.get("shop.tax-rate");
        if (!(tax instanceof Number) || ((Number) tax).doubleValue() < 0 || ((Number) tax).doubleValue() > 1) {
            throw new IllegalArgumentException("shop.tax-rate must be a number between 0 and 1, got: " + describe(tax));
        }
    }

    private static String describe(Object v) {
        return v instanceof String ? "\"" + v + "\"" : String.valueOf(v);
    }

    private void tick() {
        try {
            Files.writeString(new File(getDataFolder(), "heartbeat").toPath(), Long.toString(System.currentTimeMillis()));
        } catch (IOException e) {
            getLogger().warning("could not write heartbeat: " + e);
        }
        long mtime = new File(getDataFolder(), "config.yml").lastModified();
        if (mtime != configMtime && loadAndValidate()) {
            getLogger().info("TownCore config reloaded");
        }
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent e) {
        e.getPlayer().sendMessage(config.getString("spawn.welcome-message", "Welcome!"));
    }
}
