package io.github.mceca.npc;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.level.entity.EntityTypeTest;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;
import java.util.List;

/** What the NPC can "perceive" around it, as JSON for the brain (e.g. to put in an LLM prompt). */
final class Surroundings {
	private static final double MOB_RANGE = 16.0;
	private static final double PLAYER_RANGE = 32.0;

	private Surroundings() {
	}

	static JsonObject describe(Mannequin body, boolean walking) {
		ServerLevel level = (ServerLevel) body.level();
		Vec3 pos = body.position();
		JsonObject out = new JsonObject();

		JsonArray position = new JsonArray();
		position.add(round(pos.x));
		position.add(round(pos.y));
		position.add(round(pos.z));
		out.add("position", position);
		out.addProperty("dimension", level.dimension().identifier().getPath());
		out.addProperty("biome", level.getBiome(BlockPos.containing(pos)).unwrapKey()
				.map(k -> k.identifier().getPath()).orElse("unknown"));

		// Minecraft day: tick 0 = 06:00, 6000 = noon, 18000 = midnight.
		long dayTicks = Math.floorMod(level.getOverworldClockTime(), 24000L);
		int minutes = (int) ((dayTicks * 1440L / 24000L + 6 * 60) % 1440);
		out.addProperty("time", String.format("%02d:%02d", minutes / 60, minutes % 60));
		out.addProperty("daylight", level.isBrightOutside());
		out.addProperty("weather", level.isThundering() ? "thunder" : level.isRaining() ? "rain" : "clear");

		out.addProperty("holding", ItemNames.name(body.getItemBySlot(EquipmentSlot.MAINHAND)));
		out.addProperty("walking", walking);

		JsonArray players = new JsonArray();
		for (ServerPlayer player : level.players()) {
			double d = player.distanceTo(body);
			if (d > PLAYER_RANGE) continue;
			JsonObject p = new JsonObject();
			p.addProperty("name", player.getPlainTextName());
			p.addProperty("distance", round(d));
			p.addProperty("holding", ItemNames.name(player.getMainHandItem()));
			p.addProperty("health", round(player.getHealth()));
			players.add(p);
		}
		out.add("players", players);

		AABB box = body.getBoundingBox().inflate(MOB_RANGE);
		List<? extends Mob> mobs = level.getEntities(EntityTypeTest.forClass(Mob.class), box, Mob::isAlive);
		JsonArray mobList = new JsonArray();
		mobs.stream().sorted(Comparator.comparingDouble(m -> m.distanceTo(body))).limit(10).forEach(m -> {
			JsonObject o = new JsonObject();
			o.addProperty("type", BuiltInRegistries.ENTITY_TYPE.getKey(m.getType()).getPath());
			o.addProperty("distance", round(m.distanceTo(body)));
			mobList.add(o);
		});
		out.add("mobs", mobList);
		return out;
	}

	private static double round(double d) {
		return Math.round(d * 10.0) / 10.0;
	}
}
