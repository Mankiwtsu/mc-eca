package io.github.mceca.npc;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.github.mceca.Config;
import io.github.mceca.bridge.BridgeClient;
import io.github.mceca.bridge.CommandException;
import io.github.mceca.bridge.Json;
import net.minecraft.ChatFormatting;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.level.entity.EntityTypeTest;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.UUID;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Keeps track of all MC-ECA NPCs and routes commands and chat. Runs on the server thread only.
 */
public class NpcManager {
	/** Entity tag on every NPC body, so we can find them again after reloading the world. */
	public static final String NPC_TAG = "mceca_npc";
	/** Entity tag on speech bubbles; leftover bubbles are removed when they load. */
	public static final String BUBBLE_TAG = "mceca_bubble";

	private final MinecraftServer server;
	private final Config config;
	private final Map<String, NpcController> npcs = new LinkedHashMap<>();

	public NpcManager(MinecraftServer server, Config config) {
		this.server = server;
		this.config = config;
	}

	// ------------------------------------------------------------------ commands

	public JsonObject handle(BridgeClient client, String cmd, JsonObject msg) throws CommandException {
		switch (cmd) {
			case "spawn":
				return spawn(client, msg);
			case "players":
				return players(Json.optString(msg, "npc"));
			default:
				break;
		}

		NpcController npc = require(Json.string(msg, "npc"));
		JsonObject result = new JsonObject();
		switch (cmd) {
			case "say" -> {
				Double seconds = msg.has("seconds") && !msg.get("seconds").isJsonNull() ? msg.get("seconds").getAsDouble() : null;
				// Turn-taking: a new speaker replaces the old bubbles of NPCs standing close by,
				// so bubbles never overlap. The chat keeps the full conversation.
				for (NpcController other : npcs.values()) {
					Entity body = other.entity();
					if (other != npc && body != null && body.level() == npc.entity().level()
							&& body.distanceTo(npc.entity()) < 5.0) other.clearSpeech();
				}
				String text = Json.string(msg, "text");
				npc.say(text, seconds, config.chat_range);
				letOthersHear(npc, text, (int) Json.optDouble(msg, "chain", 0));
			}
			case "look_at" -> {
				Vec3 pos = Json.optPos(msg);
				String name = Json.optString(msg, "player");
				String other = Json.optString(msg, "target_npc");
				if (pos != null) {
					npc.lookAt(pos);
				} else if (other != null) {
					npc.lookAt(require(other).entity()); // gaze at another NPC, e.g. whoever is speaking
				} else if (name == null) {
					npc.lookAt((Entity) null);
				} else {
					npc.lookAt(player(name));
				}
			}
			case "thinking" -> npc.setThinking(Json.optBool(msg, "on", true));
			case "gesture" -> npc.gesture(Json.string(msg, "name"));
			case "emote" -> npc.emote(Json.string(msg, "name"));
			case "walk_to" -> {
				double speed = Json.optDouble(msg, "speed", 1.0);
				Vec3 pos = Json.optPos(msg);
				if (pos != null) {
					npc.walkTo(pos, Json.optDouble(msg, "distance", 0.5), speed);
				} else {
					npc.walkTo(player(Json.string(msg, "player")), Json.optDouble(msg, "distance", 3.0), speed);
				}
			}
			case "follow" -> npc.follow(player(Json.string(msg, "player")),
					Json.optDouble(msg, "distance", 3.0), Json.optDouble(msg, "speed", 1.0));
			case "stop" -> npc.stopWalking();
			case "hold" -> npc.hold(Json.optString(msg, "item"));
			case "give" -> {
				return npc.give(player(Json.string(msg, "player")), Json.optString(msg, "item"),
						(int) Json.optDouble(msg, "count", 1));
			}
			case "take" -> {
				return npc.take(player(Json.string(msg, "player")));
			}
			case "surroundings" -> {
				return npc.surroundings();
			}
			case "transcript" -> showTranscript(npc, player(Json.string(msg, "player")),
					Json.optString(msg, "text"), Json.optString(msg, "error"));
			case "remove" -> {
				npc.remove();
				npcs.remove(key(npc.name()));
			}
			default -> throw new CommandException("unknown command '" + cmd + "'");
		}
		return result;
	}

	private JsonObject spawn(BridgeClient client, JsonObject msg) throws CommandException {
		String name = Json.string(msg, "npc");
		String skin = Json.optString(msg, "skin");
		if (name.isBlank() || name.length() > 32) throw new CommandException("NPC name must be 1-32 characters");

		NpcController npc = npcs.get(key(name));
		boolean existing = npc != null && npc.entity() != null;
		if (!existing) {
			Mannequin body = findLoadedBody(name);
			if (body == null) body = spawnBody(name);
			if (npc == null) {
				npc = new NpcController(name, body);
				npcs.put(key(name), npc);
			} else {
				npc.setEntity(body);
			}
			existing = body.tickCount > 0;
		}
		if (skin != null) npc.setSkin(skin);
		npc.setLabels(Json.optBool(msg, "show_name", true), Json.optBool(msg, "show_status", true));
		npc.setNoticeRange(Json.optDouble(msg, "notice_range", 6.0));
		npc.attach(client);

		JsonObject result = new JsonObject();
		result.addProperty("existing", existing);
		return result;
	}

	private Mannequin spawnBody(String name) throws CommandException {
		List<ServerPlayer> players = server.getPlayerList().getPlayers();
		if (players.isEmpty()) throw new CommandException("no player in the world yet");
		ServerPlayer player = players.get(0);
		ServerLevel level = player.level();

		// Three blocks in front of the player (a comfortable talking distance), facing them.
		Vec3 look = player.getLookAngle();
		Vec3 flat = new Vec3(look.x, 0, look.z);
		flat = flat.lengthSqr() < 1.0E-4 ? new Vec3(0, 0, 1) : flat.normalize();
		Vec3 front = player.position().add(flat.scale(3.0));
		// If another NPC already stands there, step sideways (left, right, further left, ...).
		Vec3 side = new Vec3(-flat.z, 0, flat.x);
		Vec3 pos = front;
		for (int i = 1; i <= 8 && isOccupied(level, pos); i++) {
			pos = front.add(side.scale(2.0 * ((i + 1) / 2) * (i % 2 == 1 ? 1 : -1)));
		}

		Mannequin body = EntityTypes.MANNEQUIN.create(level, EntitySpawnReason.COMMAND);
		if (body == null) throw new CommandException("could not create the NPC entity");
		float yaw = player.getYRot() + 180f;
		body.snapTo(pos.x, pos.y, pos.z, yaw, 0f);
		body.setYHeadRot(yaw);
		body.setYBodyRot(yaw);
		body.setCustomName(Component.literal(name));
		body.setCustomNameVisible(true);
		body.setPermanentlyInvulnerable(true);
		body.addTag(NPC_TAG);
		level.addFreshEntity(body);
		return body;
	}

	private boolean isOccupied(ServerLevel level, Vec3 pos) {
		for (NpcController npc : npcs.values()) {
			Entity body = npc.entity();
			if (body != null && body.level() == level && body.position().distanceToSqr(pos) < 1.2 * 1.2) return true;
		}
		return false;
	}

	private Mannequin findLoadedBody(String name) {
		for (ServerLevel level : server.getAllLevels()) {
			List<? extends Mannequin> found = level.getEntities(EntityTypeTest.forClass(Mannequin.class),
					e -> isNpcBody(e) && name.equalsIgnoreCase(nameOf(e)));
			if (!found.isEmpty()) return found.get(0);
		}
		return null;
	}

	private JsonObject players(String npcName) {
		NpcController npc = npcName == null ? null : npcs.get(key(npcName));
		Entity body = npc == null ? null : npc.entity();
		JsonArray list = new JsonArray();
		for (ServerPlayer player : server.getPlayerList().getPlayers()) {
			JsonObject p = new JsonObject();
			p.addProperty("name", player.getPlainTextName());
			if (body != null && body.level() == player.level()) p.addProperty("distance", round(body.distanceTo(player)));
			list.add(p);
		}
		JsonObject result = new JsonObject();
		result.add("players", list);
		return result;
	}

	/**
	 * Agent-to-agent: other NPCs within hearing range hear what an NPC says ("npc_said").
	 * `chain` counts how many NPC-to-NPC replies led to this sentence (0 = not a reply to
	 * another NPC); brains use it to stop endless back-and-forth.
	 */
	private void letOthersHear(NpcController speaker, String text, int chain) {
		Entity from = speaker.entity();
		String lower = text.strip().toLowerCase(Locale.ROOT);
		if (lower.startsWith("@")) lower = lower.substring(1);
		for (NpcController other : npcs.values()) {
			Entity body = other.entity();
			if (other == speaker || body == null || body.level() != from.level() || !other.hasBrain()) continue;
			double d = body.distanceTo(from);
			if (d > config.hearing_range) continue;
			String n = other.name().toLowerCase(Locale.ROOT);
			boolean addressed = lower.startsWith(n) && (lower.length() == n.length() || !Character.isLetterOrDigit(lower.charAt(n.length())));
			JsonObject event = other.event("npc_said");
			event.addProperty("speaker", speaker.name());
			event.addProperty("text", text);
			event.addProperty("distance", round(d));
			event.addProperty("addressed", addressed);
			event.addProperty("chain", chain);
			other.broadcast(event);
		}
	}

	private ServerPlayer player(String name) throws CommandException {
		ServerPlayer player = server.getPlayerList().getPlayerByName(name);
		if (player == null) throw new CommandException("no player named '" + name + "' is online");
		return player;
	}

	private NpcController require(String name) throws CommandException {
		NpcController npc = npcs.get(key(name));
		if (npc == null || npc.entity() == null) throw new CommandException("no NPC named '" + name + "' (spawn it first)");
		return npc;
	}

	// -------------------------------------------------------------------- events

	/**
	 * A player typed in chat. The message goes to the NPC whose name it starts with
	 * ("Ava, hi" / "@Ava hi"), otherwise to the nearest NPC within hearing range.
	 */
	public void onPlayerChat(ServerPlayer player, String text) {
		NpcController target = null;
		double best = Double.MAX_VALUE;
		String lower = text.toLowerCase(Locale.ROOT);
		String stripped = lower.startsWith("@") ? lower.substring(1) : lower;

		for (NpcController npc : npcs.values()) {
			Entity body = npc.entity();
			if (body == null || body.level() != player.level()) continue;
			String n = npc.name().toLowerCase(Locale.ROOT);
			if (stripped.startsWith(n) && (stripped.length() == n.length() || !Character.isLetterOrDigit(stripped.charAt(n.length())))) {
				target = npc;
				break;
			}
			double d = body.distanceTo(player);
			if (d <= config.hearing_range && d < best) {
				best = d;
				target = npc;
			}
		}
		if (target == null) return;

		if (!target.hasBrain()) {
			player.sendOverlayMessage(Component.literal(target.name() + " has no brain connected - start your Python script")
					.withStyle(ChatFormatting.YELLOW));
			return;
		}
		JsonObject event = target.event("chat");
		event.addProperty("player", player.getPlainTextName());
		event.addProperty("text", text);
		event.addProperty("distance", round(target.entity().distanceTo(player)));
		target.broadcast(event);
	}

	// ------------------------------------------------------------------ voice

	/** Players currently holding the talk key, and the NPC that is listening to them. */
	private final Map<UUID, Listening> listening = new HashMap<>();

	private record Listening(ServerPlayer player, NpcController npc, int startTick) {
	}

	/** Max length of one voice message; after this the recording is ended automatically. */
	private static final int MAX_TALK_TICKS = 20 * 30;

	/** The player pressed or released the push-to-talk key (sent by the client mod). */
	public void onPushToTalk(ServerPlayer player, boolean pressed) {
		if (pressed) {
			if (listening.containsKey(player.getUUID())) return;
			NpcController npc = nearestListener(player);
			if (npc == null) {
				player.sendOverlayMessage(Component.literal("Nobody is close enough to hear you").withStyle(ChatFormatting.GRAY));
				return;
			}
			if (!npc.hasBrain()) {
				player.sendOverlayMessage(Component.literal(npc.name() + " has no brain connected - start your Python script")
						.withStyle(ChatFormatting.YELLOW));
				return;
			}
			listening.put(player.getUUID(), new Listening(player, npc, server.getTickCount()));
			showListening(player, npc);
			JsonObject event = npc.event("voice_start");
			event.addProperty("player", player.getPlainTextName());
			event.addProperty("distance", round(npc.entity().distanceTo(player)));
			npc.broadcast(event);
		} else {
			endTalk(player.getUUID(), false);
		}
	}

	private void endTalk(UUID id, boolean cancelled) {
		Listening l = listening.remove(id);
		if (l == null) return;
		JsonObject event = l.npc().event("voice_end");
		event.addProperty("player", l.player().getPlainTextName());
		event.addProperty("seconds", Math.round((server.getTickCount() - l.startTick()) / 2.0) / 10.0);
		if (cancelled) event.addProperty("cancelled", true);
		l.npc().broadcast(event);
		if (!cancelled) {
			l.player().sendOverlayMessage(Component.literal("... " + l.npc().name() + " is working out what you said")
					.withStyle(ChatFormatting.GRAY));
		}
	}

	private NpcController nearestListener(ServerPlayer player) {
		NpcController best = null;
		double bestDistance = config.hearing_range;
		for (NpcController npc : npcs.values()) {
			Entity body = npc.entity();
			if (body == null || body.level() != player.level()) continue;
			double d = body.distanceTo(player);
			if (d <= bestDistance) {
				bestDistance = d;
				best = npc;
			}
		}
		return best;
	}

	private void showListening(ServerPlayer player, NpcController npc) {
		player.sendOverlayMessage(Component.literal("● ").withStyle(ChatFormatting.RED)
				.append(Component.literal(npc.name() + " is listening... release the key to send").withStyle(ChatFormatting.WHITE)));
	}

	private void tickVoice() {
		if (listening.isEmpty()) return;
		int now = server.getTickCount();
		for (UUID id : List.copyOf(listening.keySet())) {
			Listening l = listening.get(id);
			if (l.player().isRemoved() || l.npc().entity() == null) {
				endTalk(id, true);
			} else if (now - l.startTick() >= MAX_TALK_TICKS) {
				endTalk(id, false);
			} else if ((now - l.startTick()) % 20 == 0) {
				showListening(l.player(), l.npc()); // the action bar fades, so refresh it
			}
		}
	}

	/** Show what the brain understood: "<Steve> [voice] come here" for nearby players. */
	private void showTranscript(NpcController npc, ServerPlayer speaker, String text, String error) {
		if (error != null) {
			speaker.sendOverlayMessage(Component.literal(error).withStyle(ChatFormatting.YELLOW));
			return;
		}
		if (text == null || text.isBlank()) {
			speaker.sendOverlayMessage(Component.literal(npc.name() + " didn't catch that - hold the key while you speak")
					.withStyle(ChatFormatting.GRAY));
			return;
		}
		Component line = Component.literal("<" + speaker.getPlainTextName() + "> ")
				.append(Component.literal("[voice] ").withStyle(ChatFormatting.GRAY))
				.append(Component.literal(text.strip()));
		for (ServerPlayer player : ((ServerLevel) speaker.level()).players()) {
			if (player.distanceTo(speaker) <= config.chat_range) player.sendSystemMessage(line);
		}
	}

	/** A player right-clicked (use) or punched (attack) an entity. Returns true if it was an NPC. */
	public boolean onPlayerInteract(ServerPlayer player, Entity entity, boolean attack) {
		if (!isNpcBody(entity)) return false;
		NpcController npc = npcs.get(key(nameOf(entity)));
		if (npc == null) return true;
		if (!npc.hasBrain()) {
			player.sendOverlayMessage(Component.literal(npc.name() + " has no brain connected - start your Python script")
					.withStyle(ChatFormatting.YELLOW));
			return true;
		}
		JsonObject event = npc.event(attack ? "hit" : "click");
		event.addProperty("player", player.getPlainTextName());
		event.addProperty("distance", round(entity.distanceTo(player)));
		if (!attack) event.addProperty("item", ItemNames.name(player.getMainHandItem()));
		npc.broadcast(event);
		return true;
	}

	/** An entity was loaded from disk or spawned. Re-link NPC bodies, drop stale bubbles. */
	public void onEntityLoad(Entity entity) {
		if (entity.entityTags().contains(BUBBLE_TAG)) {
			boolean ours = npcs.values().stream().anyMatch(n -> n.isBubble(entity));
			if (!ours) entity.discard();
			return;
		}
		if (entity instanceof Mannequin body && isNpcBody(body)) {
			String name = nameOf(body);
			NpcController npc = npcs.get(key(name));
			if (npc == null) {
				npcs.put(key(name), new NpcController(name, body));
			} else if (npc.entity() == null) {
				npc.setEntity(body);
			} else if (npc.entity() != body) {
				// An older copy with the same name (e.g. it was in an unloaded chunk when the
				// script spawned a new one). Keep the NPC the script is using.
				body.discard();
			}
		}
	}

	public void onClientGone(BridgeClient client) {
		for (NpcController npc : npcs.values()) npc.detach(client);
	}

	public void tick() {
		for (NpcController npc : npcs.values()) npc.tick(server);
		tickVoice();
	}

	public void shutdown() {
		for (NpcController npc : npcs.values()) npc.hideBubble();
		npcs.clear();
	}

	public Collection<NpcController> all() {
		return new ArrayList<>(npcs.values());
	}

	public boolean removeByName(String name) {
		NpcController npc = npcs.remove(key(name));
		if (npc != null) {
			npc.remove();
			return true;
		}
		Mannequin body = findLoadedBody(name);
		if (body != null) {
			body.discard();
			return true;
		}
		return false;
	}

	// ------------------------------------------------------------------- helpers

	static boolean isNpcBody(Entity e) {
		return e instanceof Mannequin && e.entityTags().contains(NPC_TAG);
	}

	static String nameOf(Entity e) {
		Component name = e.getCustomName();
		return name == null ? "" : name.getString();
	}

	private static String key(String name) {
		return name.toLowerCase(Locale.ROOT);
	}

	private static double round(double d) {
		return Math.round(d * 10.0) / 10.0;
	}
}
