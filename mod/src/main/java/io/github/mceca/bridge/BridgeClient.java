package io.github.mceca.bridge;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import io.github.mceca.McEca;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

/**
 * One connected brain. Reads requests on its own thread and writes replies/events on
 * another, so a slow brain never blocks the game.
 */
public class BridgeClient {
	private static final String POISON = "\u0000close";

	private final Bridge bridge;
	private final Socket socket;
	private final BlockingQueue<String> outbox = new LinkedBlockingQueue<>();
	private volatile boolean closed;

	BridgeClient(Bridge bridge, Socket socket) {
		this.bridge = bridge;
		this.socket = socket;
	}

	void start() {
		Thread reader = new Thread(this::readLoop, "mceca-client-reader");
		reader.setDaemon(true);
		reader.start();
		Thread writer = new Thread(this::writeLoop, "mceca-client-writer");
		writer.setDaemon(true);
		writer.start();
	}

	/** Queue a message for the brain. Safe to call from any thread. */
	public void send(JsonObject msg) {
		if (!closed) outbox.add(msg.toString());
	}

	void close() {
		if (closed) return;
		closed = true;
		outbox.add(POISON);
		try {
			socket.close();
		} catch (IOException ignored) {
		}
	}

	public boolean isOpen() {
		return !closed;
	}

	private void readLoop() {
		try (BufferedReader in = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.UTF_8))) {
			String line;
			while ((line = in.readLine()) != null) {
				if (line.isBlank()) continue;
				JsonObject msg;
				try {
					msg = JsonParser.parseString(line).getAsJsonObject();
				} catch (RuntimeException e) {
					send(Json.error(-1, "not valid JSON: " + line));
					continue;
				}
				bridge.onRequest(this, msg);
			}
		} catch (IOException e) {
			// connection dropped
		} finally {
			close();
			bridge.onDisconnect(this);
		}
	}

	private void writeLoop() {
		try (Writer out = new OutputStreamWriter(socket.getOutputStream(), StandardCharsets.UTF_8)) {
			while (true) {
				String line = outbox.take();
				if (line == POISON) return;
				out.write(line);
				out.write('\n');
				if (outbox.isEmpty()) out.flush();
			}
		} catch (IOException | InterruptedException e) {
			if (!closed) McEca.LOGGER.debug("MC-ECA writer stopped: {}", e.toString());
		}
	}
}
