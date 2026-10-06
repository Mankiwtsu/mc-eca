package io.github.mceca;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Settings, stored in {@code .minecraft/config/mceca.json}. The file is created with
 * default values the first time the game starts.
 */
public class Config {
	/** TCP port the brain (Python) connects to. */
	public int port = 25599;
	/**
	 * Network address the bridge listens on. "127.0.0.1" = only scripts on this computer can
	 * connect (safe default). "0.0.0.0" = scripts on other computers in the network can connect
	 * too, e.g. a Wizard-of-Oz operator on a second laptop.
	 */
	public String bind_address = "127.0.0.1";
	/** A player within this many blocks of an NPC is talking to it. */
	public double hearing_range = 8.0;
	/** Players within this many blocks see what the NPC says in their chat. */
	public double chat_range = 32.0;

	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	public static Config load() {
		Path file = FabricLoader.getInstance().getConfigDir().resolve("mceca.json");
		Config config = new Config();
		try {
			if (Files.exists(file)) {
				Config read = GSON.fromJson(Files.readString(file), Config.class);
				if (read != null) config = read;
			}
			Files.writeString(file, GSON.toJson(config));
		} catch (IOException | RuntimeException e) {
			McEca.LOGGER.warn("Could not read/write {}, using defaults: {}", file, e.toString());
		}
		// MCECA_PORT overrides the port (e.g. a second Minecraft for testing next to a running one).
		String envPort = System.getenv("MCECA_PORT");
		if (envPort != null && envPort.matches("\\d+")) config.port = Integer.parseInt(envPort);
		return config;
	}
}
