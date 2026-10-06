package io.github.mceca.bridge;

import com.google.gson.JsonObject;
import io.github.mceca.McEca;
import io.github.mceca.npc.NpcManager;
import net.minecraft.server.MinecraftServer;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Local TCP server the brain connects to.
 *
 * Protocol: every message is one line of JSON (newline-delimited JSON).
 * <ul>
 *   <li>brain -> mod (request): {@code {"id": 1, "cmd": "say", "npc": "Ava", "text": "Hi"}}</li>
 *   <li>mod -> brain (reply):   {@code {"re": 1, "ok": true, "result": {...}}} or {@code {"re": 1, "ok": false, "error": "..."}}</li>
 *   <li>mod -> brain (event):   {@code {"event": "chat", "npc": "Ava", "player": "Steve", "text": "Hello", "distance": 3.1}}</li>
 * </ul>
 * See docs/03-api-reference.md for every command.
 *
 * By default only accepts connections from this computer (127.0.0.1), see Config.bind_address.
 */
public class Bridge {
	/**
	 * Version of the JSON protocol. Bump it when commands or events change. Older clients
	 * keep working (the protocol only grows); newer clients get a clear error from older mods.
	 *   1 = v0.1: say, thinking, look_at, gesture, players, remove; chat event
	 *   2 = v0.2: + emote, walk_to, follow, stop, hold, give, take, surroundings, look_at a
	 *       position, spawn.notice_range; player_near, player_left, click, hit, arrived, stuck
	 *   3 = v0.3: + transcript; voice_start, voice_end (push-to-talk)
	 *   4 = v0.4: + say.chain; npc_said (NPCs hear each other)
	 */
	public static final int PROTOCOL_VERSION = 4;

	private final MinecraftServer server;
	private final NpcManager npcs;
	private final String bindAddress;
	private final int port;
	private final List<BridgeClient> clients = new CopyOnWriteArrayList<>();
	private volatile ServerSocket serverSocket;
	private volatile String failure;

	public Bridge(MinecraftServer server, NpcManager npcs, String bindAddress, int port) {
		this.server = server;
		this.npcs = npcs;
		this.bindAddress = bindAddress;
		this.port = port;
	}

	public void start() {
		try {
			ServerSocket socket = new ServerSocket();
			socket.setReuseAddress(true);
			socket.bind(new InetSocketAddress(InetAddress.getByName(bindAddress), port));
			serverSocket = socket;
		} catch (IOException e) {
			failure = "cannot listen on " + bindAddress + ":" + port + " (" + e.getMessage()
					+ "). Is another world or Minecraft open?";
			McEca.LOGGER.error("MC-ECA bridge could not start: {}", failure);
			return;
		}
		Thread accept = new Thread(this::acceptLoop, "mceca-bridge");
		accept.setDaemon(true);
		accept.start();
		McEca.LOGGER.info("MC-ECA bridge listening on {}:{}", bindAddress, port);
	}

	public void stop() {
		ServerSocket socket = serverSocket;
		serverSocket = null;
		if (socket != null) {
			try {
				socket.close();
			} catch (IOException ignored) {
			}
		}
		for (BridgeClient client : clients) client.close();
		clients.clear();
	}

	private void acceptLoop() {
		while (serverSocket != null) {
			try {
				Socket socket = serverSocket.accept();
				BridgeClient client = new BridgeClient(this, socket);
				clients.add(client);
				client.start();
				McEca.LOGGER.info("Brain connected from {}", socket.getRemoteSocketAddress());
			} catch (IOException e) {
				// Socket closed by stop(), or a broken connection attempt.
			}
		}
	}

	/** Called on the client's reader thread for every incoming line. */
	void onRequest(BridgeClient client, JsonObject msg) {
		int id = msg.has("id") ? msg.get("id").getAsInt() : -1;
		String cmd = msg.has("cmd") ? msg.get("cmd").getAsString() : "";

		if (cmd.equals("hello")) {
			int protocol = msg.has("protocol") ? msg.get("protocol").getAsInt() : PROTOCOL_VERSION;
			if (protocol > PROTOCOL_VERSION) {
				client.send(Json.error(id, "protocol version mismatch: this MC-ECA mod speaks version " + PROTOCOL_VERSION
						+ ", your client needs version " + protocol + ". Update the MC-ECA mod (.jar)."));
				return;
			}
			JsonObject result = new JsonObject();
			result.addProperty("server", "mc-eca");
			result.addProperty("protocol", PROTOCOL_VERSION);
			client.send(Json.ok(id, result));
			return;
		}

		// Everything else touches the world, so it must run on the server thread.
		server.execute(() -> {
			try {
				JsonObject result = npcs.handle(client, cmd, msg);
				client.send(Json.ok(id, result));
			} catch (CommandException e) {
				client.send(Json.error(id, e.getMessage()));
			} catch (RuntimeException e) {
				McEca.LOGGER.error("MC-ECA command '{}' failed", cmd, e);
				client.send(Json.error(id, "internal error: " + e));
			}
		});
	}

	void onDisconnect(BridgeClient client) {
		clients.remove(client);
		McEca.LOGGER.info("Brain disconnected");
		server.execute(() -> npcs.onClientGone(client));
	}

	public int port() {
		return port;
	}

	public String bindAddress() {
		return bindAddress;
	}

	public String failure() {
		return failure;
	}

	public int clientCount() {
		return clients.size();
	}
}
