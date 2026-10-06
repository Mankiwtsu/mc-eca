package io.github.mceca.npc;

import com.google.gson.JsonObject;
import com.mojang.math.Transformation;
import com.mojang.serialization.JsonOps;
import io.github.mceca.bridge.BridgeClient;
import io.github.mceca.bridge.CommandException;
import io.github.mceca.bridge.Json;
import net.minecraft.ChatFormatting;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextColor;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Brightness;
import net.minecraft.util.Mth;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Display;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.Pose;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.component.ResolvableProfile;
import net.minecraft.world.item.component.SwingAnimation;
import net.minecraft.world.phys.Vec3;
import org.joml.Vector3f;

import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * One NPC: its body (a vanilla mannequin entity), speech bubble, gaze, gestures, emotions,
 * walking, items and what it notices. {@link #tick} runs every game tick (20x per second).
 */
public class NpcController {
	public static final List<String> GESTURES = List.of("nod", "shake", "wave", "crouch", "jump");
	public static final List<String> EMOTES = List.of("happy", "love", "angry", "sad", "surprised", "confused");
	private static final List<String> DEFAULT_SKINS = List.of("steve", "alex", "ari", "efe", "kai", "makena", "noor", "sunny", "zuri");

	/** How many characters of a sentence appear per tick (typewriter effect, ~40 chars/s). */
	private static final int TYPE_SPEED = 2;
	private static final int MAX_BUBBLE_CHARS = 400;
	private static final int BUBBLE_BACKGROUND = 0xE6FFFFFF; // mostly opaque white
	/** Text size of the bubble (1 = size of a name tag) and its width in pixels at that size. */
	private static final float BUBBLE_SCALE = 0.8f;
	private static final int BUBBLE_LINE_WIDTH = 190;
	private static final TextColor BUBBLE_TEXT = TextColor.fromRgb(0x202020);
	/** Gap between the top of the NPC (its hitbox) and the bubble: room for the name tag. */
	private static final double BUBBLE_GAP = 0.85;
	/** Max head/body turn per tick while looking at something (degrees). */
	private static final float TURN_SPEED = 20f;
	/** How far the head can turn away from the body (e.g. looking at you while walking). */
	private static final float MAX_HEAD_TURN = 70f;

	private final String name;
	private Mannequin body;
	private final Set<BridgeClient> brains = new LinkedHashSet<>();

	// gaze: the body faces `yaw`, the head `headYaw`
	private Entity lookTarget; // a player or another NPC
	private Vec3 lookPos;
	private float yaw;
	private float headYaw;
	private float pitch;

	// gesture + emotion
	private String gesture;
	private int gestureTick;
	private String emote;
	private int emoteTick;

	// walking
	private final NpcMovement movement = new NpcMovement();

	// noticing players: uuid -> name of players currently within noticeRange
	private double noticeRange = 6.0;
	private final Map<UUID, String> nearby = new HashMap<>();

	// speech bubble
	private Display.TextDisplay bubble;
	private String bubbleText = "";
	private int shownChars;
	private int bubbleTicksLeft;
	private boolean thinking;
	private int thinkingTicks;

	NpcController(String name, Mannequin body) {
		this.name = name;
		setEntity(body);
	}

	// ------------------------------------------------------------------ speech

	void say(String text, Double seconds, double chatRange) {
		thinking = false;
		String clean = text.strip();
		if (clean.isEmpty()) return;
		bubbleText = clean.length() > MAX_BUBBLE_CHARS ? clean.substring(0, MAX_BUBBLE_CHARS - 1) + "…" : clean;
		shownChars = 0;
		int typingTicks = bubbleText.length() / TYPE_SPEED;
		double readSeconds = seconds != null ? seconds : Math.min(20.0, 3.0 + bubbleText.length() / 15.0);
		bubbleTicksLeft = typingTicks + (int) (readSeconds * 20);

		// Also put it in the chat of nearby players, so it can be read back later.
		Component line = Component.literal("<").append(Component.literal(name).withStyle(ChatFormatting.AQUA))
				.append(Component.literal("> " + clean));
		for (ServerPlayer player : ((ServerLevel) body.level()).players()) {
			if (player.distanceTo(body) <= chatRange) player.sendSystemMessage(line);
		}
	}

	/** Remove what the NPC is currently saying (but keep a "thinking" bubble). */
	void clearSpeech() {
		bubbleTicksLeft = 0;
		if (!thinking) hideBubble();
	}

	void setThinking(boolean on) {
		thinking = on;
		thinkingTicks = 0;
		if (on) bubbleTicksLeft = 0;
	}

	// -------------------------------------------------------- gaze, gesture, emotion

	void lookAt(Entity target) {
		lookTarget = target;
		lookPos = null;
	}

	void lookAt(Vec3 pos) {
		lookTarget = null;
		lookPos = pos;
	}

	void gesture(String name) throws CommandException {
		String g = name.toLowerCase(Locale.ROOT);
		if (!GESTURES.contains(g)) throw new CommandException("unknown gesture '" + name + "', choose from " + GESTURES);
		gesture = g;
		gestureTick = 0;
	}

	void emote(String name) throws CommandException {
		String e = name.toLowerCase(Locale.ROOT);
		if (!EMOTES.contains(e)) throw new CommandException("unknown emotion '" + name + "', choose from " + EMOTES);
		emote = e;
		emoteTick = 0;
	}

	// ------------------------------------------------------------------- walking

	void walkTo(Vec3 pos, double distance, double speed) {
		movement.walkTo(pos, distance, speed);
	}

	void walkTo(ServerPlayer player, double distance, double speed) {
		movement.walkTo(player, distance, speed);
	}

	void follow(ServerPlayer player, double distance, double speed) {
		movement.follow(player, distance, speed);
	}

	void stopWalking() {
		movement.stop(body);
	}

	// --------------------------------------------------------------------- items

	void hold(String item) throws CommandException {
		body.setItemSlot(EquipmentSlot.MAINHAND, item == null ? ItemStack.EMPTY : new ItemStack(ItemNames.parse(item)));
	}

	/** Give `count` of `item` (or what the NPC holds, if item is null) to the player. */
	JsonObject give(ServerPlayer player, String item, int count) throws CommandException {
		ItemStack held = body.getItemBySlot(EquipmentSlot.MAINHAND);
		Item what;
		boolean fromHand = item == null;
		if (fromHand) {
			if (held.isEmpty()) throw new CommandException(name + " is not holding anything to give (use hold() or pass an item)");
			what = held.getItem();
		} else {
			what = ItemNames.parse(item);
		}
		ItemStack stack = new ItemStack(what, Mth.clamp(count, 1, 64));
		String given = ItemNames.name(stack);
		int givenCount = stack.getCount();
		if (!player.getInventory().add(stack) && !stack.isEmpty()) {
			// Inventory full: drop it at the player's feet.
			ServerLevel level = (ServerLevel) player.level();
			level.addFreshEntity(new ItemEntity(level, player.getX(), player.getY() + 0.5, player.getZ(), stack));
		}
		if (fromHand || ItemStack.isSameItem(held, new ItemStack(what))) body.setItemSlot(EquipmentSlot.MAINHAND, ItemStack.EMPTY);
		body.swing(InteractionHand.MAIN_HAND, SwingAnimation.DEFAULT, true);

		JsonObject result = new JsonObject();
		result.addProperty("item", given);
		result.addProperty("count", givenCount);
		return result;
	}

	/** Take one item from the player's hand; the NPC then holds it. */
	JsonObject take(ServerPlayer player) throws CommandException {
		ItemStack hand = player.getMainHandItem();
		if (hand.isEmpty()) throw new CommandException(player.getPlainTextName() + " has nothing in their hand");
		ItemStack taken = hand.copyWithCount(1);
		hand.shrink(1);
		body.setItemSlot(EquipmentSlot.MAINHAND, taken);
		body.swing(InteractionHand.MAIN_HAND, SwingAnimation.DEFAULT, true);

		JsonObject result = new JsonObject();
		result.addProperty("item", ItemNames.name(taken));
		result.addProperty("count", 1);
		return result;
	}

	JsonObject surroundings() {
		return Surroundings.describe(body, movement.isMoving());
	}

	// ---------------------------------------------------------------- appearance

	void setSkin(String skin) throws CommandException {
		String s = skin.strip();
		JsonObject json = new JsonObject();
		String lower = s.toLowerCase(Locale.ROOT);
		if (DEFAULT_SKINS.contains(lower)) {
			// Built-in skins: Alex has slim arms, the rest wide (same as the vanilla defaults).
			String model = lower.equals("alex") ? "slim" : "wide";
			json.addProperty("texture", "entity/player/" + model + "/" + lower);
			json.addProperty("model", model);
		} else if (s.matches("[A-Za-z0-9_]{3,16}")) {
			json.addProperty("name", s); // skin of a real Minecraft account (needs internet)
		} else {
			throw new CommandException("skin must be a default skin " + DEFAULT_SKINS + " or a Minecraft username");
		}
		ResolvableProfile profile = ResolvableProfile.CODEC.parse(JsonOps.INSTANCE, json)
				.getOrThrow(err -> new IllegalArgumentException("bad skin: " + err));
		body.setProfile(profile);
	}

	/** Show or hide the name above the NPC and the "connected" line under it. */
	void setLabels(boolean showName, boolean showStatus) {
		body.setCustomNameVisible(showName);
		body.setHideDescription(!showStatus);
	}

	void setNoticeRange(double range) {
		noticeRange = Math.max(0, range);
	}

	void remove() {
		hideBubble();
		movement.stop(body);
		if (body != null) body.discard();
		body = null;
	}

	// -------------------------------------------------------------------- brains

	void attach(BridgeClient client) {
		brains.add(client);
		// Report players who are already close by to the new brain.
		nearby.clear();
		updateStatus();
	}

	void detach(BridgeClient client) {
		if (brains.remove(client)) {
			thinking = false;
			if (!hasBrain()) movement.stop(body);
			updateStatus();
		}
	}

	boolean hasBrain() {
		brains.removeIf(c -> !c.isOpen());
		return !brains.isEmpty();
	}

	void broadcast(JsonObject event) {
		for (BridgeClient c : brains) c.send(event);
	}

	JsonObject event(String type) {
		JsonObject e = Json.event(type);
		e.addProperty("npc", name);
		return e;
	}

	/** The small line under the NPC's name shows whether a brain (script) is connected. */
	private void updateStatus() {
		if (body == null) return;
		body.setDescription(hasBrain()
				? Component.literal("● connected").withStyle(ChatFormatting.GREEN)
				: Component.literal("○ no brain").withStyle(ChatFormatting.GRAY));
	}

	// ---------------------------------------------------------------------- tick

	void tick(MinecraftServer server) {
		if (body == null) return;
		if (body.isRemoved()) {
			// Chunk unloaded or entity killed; it is re-linked by NpcManager.onEntityLoad.
			hideBubble();
			return;
		}
		tickMovement();
		tickGaze();
		tickGesture();
		tickEmote();
		tickBubble();
		if (body.tickCount % 5 == 0) tickNotice();
	}

	private void tickMovement() {
		NpcMovement.Result result = movement.tick(body, yaw);
		if (movement.isMoving()) yaw = movement.moveYaw();
		if (result == NpcMovement.Result.ARRIVED) broadcast(event("arrived"));
		if (result == NpcMovement.Result.STUCK) broadcast(event("stuck"));
	}

	private void tickGaze() {
		if (lookTarget != null && (lookTarget.isRemoved() || lookTarget.level() != body.level())) lookTarget = null;
		Vec3 target = lookTarget != null ? lookTarget.getEyePosition() : lookPos;
		boolean walking = movement.isMoving();

		float desiredHead = yaw;
		float desiredPitch = walking ? 0f : pitch;
		if (target != null) {
			Vec3 from = body.getEyePosition();
			double dx = target.x - from.x, dy = target.y - from.y, dz = target.z - from.z;
			desiredHead = (float) (Mth.atan2(dz, dx) * Mth.RAD_TO_DEG) - 90f;
			desiredPitch = (float) -(Mth.atan2(dy, Math.sqrt(dx * dx + dz * dz)) * Mth.RAD_TO_DEG);
			// Standing still: turn the whole body. Walking: the body faces the way it walks.
			if (!walking) yaw += Mth.clamp(Mth.wrapDegrees(desiredHead - yaw), -TURN_SPEED, TURN_SPEED);
		}
		headYaw += Mth.clamp(Mth.wrapDegrees(desiredHead - headYaw), -TURN_SPEED, TURN_SPEED);
		float relative = Mth.wrapDegrees(headYaw - yaw);
		if (Math.abs(relative) > MAX_HEAD_TURN) headYaw = yaw + Math.copySign(MAX_HEAD_TURN, relative);
		pitch += Mth.clamp(desiredPitch - pitch, -TURN_SPEED, TURN_SPEED);

		float yawOffset = 0f, pitchOffset = 0f;
		if ("nod".equals(gesture)) {
			// two dips of the head, 1 second
			pitchOffset = 22f * Math.abs(Mth.sin(gestureTick / 10f * Mth.PI));
		} else if ("shake".equals(gesture)) {
			// two left-right turns of the head, 1 second
			yawOffset = 28f * Mth.sin(gestureTick / 10f * Mth.TWO_PI);
		}

		body.setYRot(yaw);
		body.setYBodyRot(yaw);
		body.setYHeadRot(headYaw + yawOffset);
		body.setXRot(Mth.clamp(pitch + pitchOffset, -90f, 90f));
	}

	private void tickGesture() {
		if (gesture == null) return;
		int t = gestureTick++;
		switch (gesture) {
			case "nod", "shake" -> {
				if (t >= 20) gesture = null;
			}
			case "wave" -> {
				if (t % 6 == 0) body.swing(InteractionHand.MAIN_HAND, SwingAnimation.DEFAULT, true);
				if (t >= 18) gesture = null;
			}
			case "crouch" -> {
				body.setPose(t < 8 || (t >= 12 && t < 20) ? Pose.CROUCHING : Pose.STANDING);
				if (t >= 20) {
					body.setPose(Pose.STANDING);
					gesture = null;
				}
			}
			case "jump" -> {
				if (t == 0 && body.onGround()) body.setDeltaMovement(body.getDeltaMovement().add(0, 0.42, 0));
				if (t >= 10) gesture = null;
			}
			default -> gesture = null;
		}
	}

	/** Emotions are shown as particles around the head, in three bursts over one second. */
	private void tickEmote() {
		if (emote == null) return;
		int t = emoteTick++;
		if (t % 8 == 0) {
			ServerLevel level = (ServerLevel) body.level();
			Vec3 head = body.getEyePosition().add(0, 0.5, 0);
			switch (emote) {
				case "happy" -> particles(level, ParticleTypes.HAPPY_VILLAGER, head, 8, 0.4, 0.0);
				case "love" -> particles(level, ParticleTypes.HEART, head, 3, 0.35, 0.0);
				case "angry" -> particles(level, ParticleTypes.ANGRY_VILLAGER, head, 3, 0.35, 0.0);
				case "sad" -> particles(level, ParticleTypes.FALLING_WATER, body.getEyePosition(), 10, 0.25, 0.0);
				case "surprised" -> particles(level, ParticleTypes.CRIT, head, 12, 0.3, 0.2);
				case "confused" -> particles(level, ParticleTypes.SMOKE, head, 8, 0.25, 0.01);
				default -> {
				}
			}
		}
		if (t >= 20) emote = null;
	}

	private static void particles(ServerLevel level, ParticleOptions type, Vec3 at, int count, double spread, double speed) {
		level.sendParticles(type, at.x, at.y, at.z, count, spread, spread * 0.5, spread, speed);
	}

	/** Report players coming within / leaving noticeRange (checked 4x per second). */
	private void tickNotice() {
		if (noticeRange <= 0 || !hasBrain()) return;
		ServerLevel level = (ServerLevel) body.level();
		for (ServerPlayer player : level.players()) {
			double d = player.distanceTo(body);
			if (d <= noticeRange && !nearby.containsKey(player.getUUID())) {
				nearby.put(player.getUUID(), player.getPlainTextName());
				JsonObject e = event("player_near");
				e.addProperty("player", player.getPlainTextName());
				e.addProperty("distance", Math.round(d * 10.0) / 10.0);
				broadcast(e);
			}
		}
		nearby.entrySet().removeIf(entry -> {
			ServerPlayer player = level.getServer().getPlayerList().getPlayer(entry.getKey());
			boolean gone = player == null || player.level() != level;
			double d = gone ? -1 : player.distanceTo(body);
			if (gone || d > noticeRange + 1.0) { // +1 block so standing on the edge doesn't flicker
				JsonObject e = event("player_left");
				e.addProperty("player", entry.getValue());
				if (!gone) e.addProperty("distance", Math.round(d * 10.0) / 10.0);
				broadcast(e);
				return true;
			}
			return false;
		});
	}

	private void tickBubble() {
		String text;
		if (thinking) {
			if (++thinkingTicks > 20 * 60) thinking = false; // safety: never think longer than a minute
			int dots = 1 + (thinkingTicks / 6) % 3;
			text = ".".repeat(dots);
		} else if (bubbleTicksLeft > 0) {
			bubbleTicksLeft--;
			shownChars = Math.min(bubbleText.length(), shownChars + TYPE_SPEED);
			text = bubbleText.substring(0, shownChars);
		} else {
			hideBubble();
			return;
		}

		if (bubble == null || bubble.isRemoved()) bubble = createBubble();
		if (bubble == null) return;
		bubble.setText(Component.literal(text).withStyle(s -> s.withColor(BUBBLE_TEXT)));
		Vec3 pos = bubblePos();
		if (bubble.position().distanceToSqr(pos) > 1.0E-4) bubble.setPos(pos);
	}

	private Display.TextDisplay createBubble() {
		ServerLevel level = (ServerLevel) body.level();
		Display.TextDisplay display = EntityTypes.TEXT_DISPLAY.create(level, EntitySpawnReason.COMMAND);
		if (display == null) return null;
		Vec3 pos = bubblePos();
		display.snapTo(pos.x, pos.y, pos.z, 0f, 0f);
		display.setBillboardConstraints(Display.BillboardConstraints.CENTER);
		display.setLineWidth(BUBBLE_LINE_WIDTH);
		display.setTransformation(new Transformation(null, null, new Vector3f(BUBBLE_SCALE), null));
		display.setBackgroundColor(BUBBLE_BACKGROUND);
		display.setViewRange(0.5f);
		display.setBrightnessOverride(Brightness.FULL_BRIGHT); // readable at night and in caves
		display.setPosRotInterpolationDuration(2);
		display.addTag(NpcManager.BUBBLE_TAG);
		bubble = display; // set before adding, so onEntityLoad recognises it as ours
		level.addFreshEntity(display);
		return display;
	}

	/** Just above the name tag; follows the NPC when it crouches, jumps or walks. */
	private Vec3 bubblePos() {
		return body.position().add(0, body.getBbHeight() + BUBBLE_GAP, 0);
	}

	void hideBubble() {
		if (bubble != null) {
			bubble.discard();
			bubble = null;
		}
	}

	// ------------------------------------------------------------------- getters

	boolean isBubble(Entity e) {
		return e == bubble;
	}

	void setEntity(Mannequin body) {
		this.body = body;
		this.yaw = body.getYRot();
		this.headYaw = body.getYHeadRot();
		this.pitch = body.getXRot();
		updateStatus();
	}

	public String name() {
		return name;
	}

	public Entity entity() {
		return body == null || body.isRemoved() ? null : body;
	}

	public int brainCount() {
		hasBrain();
		return brains.size();
	}
}
