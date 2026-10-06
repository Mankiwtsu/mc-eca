package io.github.mceca.bridge;

import com.google.gson.JsonObject;
import net.minecraft.world.phys.Vec3;

/** Small helpers to build protocol messages. */
public final class Json {
	private Json() {
	}

	public static JsonObject ok(int id, JsonObject result) {
		JsonObject msg = new JsonObject();
		msg.addProperty("re", id);
		msg.addProperty("ok", true);
		msg.add("result", result == null ? new JsonObject() : result);
		return msg;
	}

	public static JsonObject error(int id, String error) {
		JsonObject msg = new JsonObject();
		msg.addProperty("re", id);
		msg.addProperty("ok", false);
		msg.addProperty("error", error);
		return msg;
	}

	public static JsonObject event(String name) {
		JsonObject msg = new JsonObject();
		msg.addProperty("event", name);
		return msg;
	}

	public static String string(JsonObject msg, String key) throws CommandException {
		if (!msg.has(key) || msg.get(key).isJsonNull()) throw new CommandException("missing '" + key + "'");
		return msg.get(key).getAsString();
	}

	public static boolean optBool(JsonObject msg, String key, boolean fallback) {
		return msg.has(key) && !msg.get(key).isJsonNull() ? msg.get(key).getAsBoolean() : fallback;
	}

	public static double optDouble(JsonObject msg, String key, double fallback) {
		return msg.has(key) && !msg.get(key).isJsonNull() ? msg.get(key).getAsDouble() : fallback;
	}

	/** A position given as "x", "y", "z" fields, or null if there is none. */
	public static Vec3 optPos(JsonObject msg) throws CommandException {
		if (!msg.has("x") && !msg.has("y") && !msg.has("z")) return null;
		if (!msg.has("x") || !msg.has("y") || !msg.has("z")) throw new CommandException("a position needs x, y and z");
		return new Vec3(msg.get("x").getAsDouble(), msg.get("y").getAsDouble(), msg.get("z").getAsDouble());
	}

	public static String optString(JsonObject msg, String key) {
		return msg.has(key) && !msg.get(key).isJsonNull() ? msg.get(key).getAsString() : null;
	}
}
