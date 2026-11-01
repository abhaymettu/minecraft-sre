package sre.audittrail;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileWriter;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.AsyncPlayerChatEvent;
import org.bukkit.event.player.PlayerCommandPreprocessEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;
import org.bukkit.scheduler.BukkitTask;

public final class AuditTrail extends JavaPlugin implements Listener {
    private static final long BYTES_PER_SECOND = 4_000_000L;
    private static final long ROTATE_BYTES = 50L * 1024 * 1024;
    private static final String[] PACKETS = {
        "ClientboundMoveEntityPacket$Pos", "ClientboundSetEntityMotionPacket", "ClientboundTeleportEntityPacket",
        "ClientboundBlockUpdatePacket", "ServerboundMovePlayerPacket$PosRot", "ClientboundSetTimePacket",
        "ClientboundLevelChunkWithLightPacket", "ServerboundKeepAlivePacket", "ClientboundRotateHeadPacket",
    };

    private BufferedWriter audit;
    private long configMtime;
    private BukkitTask debugTask;
    private OutputStream trace;
    private long traceBytes;
    private int traceIndex;
    private long lastWriteNanos;
    private long seq;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        try {
            audit = new BufferedWriter(new FileWriter(new File(getDataFolder(), "audit.log"), StandardCharsets.UTF_8, true));
        } catch (IOException e) {
            throw new IllegalStateException("cannot open audit.log", e);
        }
        reload();
        getServer().getPluginManager().registerEvents(this, this);
        getServer().getScheduler().runTaskTimer(this, () -> {
            if (configFile().lastModified() != configMtime) reload();
        }, 40L, 40L);
    }

    @Override
    public void onDisable() {
        stopDebug();
        try {
            if (audit != null) audit.close();
        } catch (IOException ignored) {
        }
    }

    private File configFile() {
        return new File(getDataFolder(), "config.yml");
    }

    private void reload() {
        configMtime = configFile().lastModified();
        reloadConfig();
        boolean debug = getConfig().getBoolean("debug", false);
        getLogger().info("AuditTrail config reloaded (debug=" + debug + ")");
        if (debug) startDebug();
        else stopDebug();
    }

    private synchronized void startDebug() {
        if (debugTask != null) return;
        lastWriteNanos = System.nanoTime();
        debugTask = getServer().getScheduler().runTaskTimerAsynchronously(this, this::writeTrace, 5L, 5L);
    }

    private synchronized void stopDebug() {
        if (debugTask != null) {
            debugTask.cancel();
            debugTask = null;
        }
        closeTrace();
    }

    private synchronized void writeTrace() {
        if (debugTask == null) return;
        long now = System.nanoTime();
        long budget = Math.min(BYTES_PER_SECOND * (now - lastWriteNanos) / 1_000_000_000L, BYTES_PER_SECOND);
        lastWriteNanos = now;
        try {
            while (budget > 0) {
                if (trace == null || traceBytes >= ROTATE_BYTES) openNextTrace();
                byte[] chunk = traceChunk((int) Math.min(budget, 65536));
                trace.write(chunk);
                traceBytes += chunk.length;
                budget -= chunk.length;
            }
            trace.flush();
        } catch (IOException e) {
            getLogger().warning("debug trace write failed: " + e);
        }
    }

    private void openNextTrace() throws IOException {
        closeTrace();
        File dir = new File(getDataFolder(), "debug");
        dir.mkdirs();
        File f;
        do {
            f = new File(dir, "trace-" + traceIndex++ + ".log");
        } while (f.exists());
        trace = new FileOutputStream(f);
        traceBytes = 0;
    }

    private void closeTrace() {
        try {
            if (trace != null) trace.close();
        } catch (IOException ignored) {
        }
        trace = null;
    }

    private byte[] traceChunk(int size) {
        ThreadLocalRandom r = ThreadLocalRandom.current();
        StringBuilder sb = new StringBuilder(size + 256);
        String ts = Instant.now().toString();
        while (sb.length() < size) {
            sb.append(ts).append(" [netty-io-").append(r.nextInt(8)).append("] TRACE seq=").append(seq++)
                .append(' ').append(PACKETS[r.nextInt(PACKETS.length)])
                .append(" eid=").append(r.nextInt(100000))
                .append(" x=").append(r.nextInt(-3000, 3000)).append('.').append(r.nextInt(1000))
                .append(" y=").append(r.nextInt(-64, 320)).append('.').append(r.nextInt(1000))
                .append(" z=").append(r.nextInt(-3000, 3000)).append('.').append(r.nextInt(1000))
                .append(" bytes=").append(r.nextInt(12, 4096))
                .append(" payload=").append(Long.toHexString(r.nextLong())).append(Long.toHexString(r.nextLong()))
                .append('\n');
        }
        sb.setLength(size);
        return sb.toString().getBytes(StandardCharsets.US_ASCII);
    }

    private synchronized void record(String player, String event, String text) {
        try {
            audit.write(Instant.now() + " " + player + " " + event + " " + text.replace('\n', ' ') + "\n");
            audit.flush();
        } catch (IOException e) {
            getLogger().warning("could not write audit.log: " + e);
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onJoin(PlayerJoinEvent e) {
        record(e.getPlayer().getName(), "join", e.getPlayer().getAddress() == null ? "" : e.getPlayer().getAddress().getAddress().getHostAddress());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onQuit(PlayerQuitEvent e) {
        record(e.getPlayer().getName(), "quit", "");
    }

    @SuppressWarnings("deprecation")
    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onChat(AsyncPlayerChatEvent e) {
        record(e.getPlayer().getName(), "chat", e.getMessage());
    }

    @EventHandler(priority = EventPriority.MONITOR, ignoreCancelled = true)
    public void onCommand(PlayerCommandPreprocessEvent e) {
        record(e.getPlayer().getName(), "command", e.getMessage());
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (args.length == 1 && args[0].equalsIgnoreCase("reload")) {
            reload();
            sender.sendMessage("AuditTrail reloaded (debug=" + getConfig().getBoolean("debug", false) + ")");
            return true;
        }
        return false;
    }
}
