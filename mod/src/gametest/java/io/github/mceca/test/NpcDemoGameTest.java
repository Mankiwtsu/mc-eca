package io.github.mceca.test;

import io.github.mceca.McEca;
import io.github.mceca.npc.NpcController;
import io.github.mceca.npc.NpcManager;
import net.fabricmc.fabric.api.client.gametest.v1.FabricClientGameTest;
import net.fabricmc.fabric.api.client.gametest.v1.context.ClientGameTestContext;
import net.fabricmc.fabric.api.client.gametest.v1.context.TestSingleplayerContext;
import com.mojang.blaze3d.platform.InputConstants;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.phys.Vec3;

import java.util.Comparator;

/**
 * Drives a real Minecraft client: creates a world, waits until a brain script has
 * spawned an NPC, then plays a scenario and takes screenshots (run/screenshots).
 *
 * Start a brain first (e.g. {@code python tools/test_brain.py}), then run
 * {@code ./gradlew runClientGameTest}.
 *
 * Simple mode: MCECA_TEST_MESSAGES="Hello|How are you?" sends each message and takes a
 * screenshot right after it and halfway through MCECA_TEST_REPLY_TICKS (default 120).
 *
 * Scenario mode: MCECA_TEST_STEPS is a list of steps separated by "|":
 * <pre>
 *   chat:TEXT      the player says TEXT
 *   wait:TICKS     wait (20 ticks = 1 second)
 *   shot:NAME      take a screenshot
 *   cmd:COMMAND    run a server command, e.g. "cmd:tp @p ~5 ~ ~" (no leading slash)
 *   use            right-click what the crosshair points at
 *   attack         left-click (punch) what the crosshair points at
 *   walk:TICKS     hold the forward key
 *   look:YAW,PITCH turn the camera
 *   aim            point the camera at the chest of the nearest NPC
 *   talk_start     press and hold the push-to-talk key (V)
 *   talk_end       release it
 * </pre>
 */
public class NpcDemoGameTest implements FabricClientGameTest {
	@Override
	public void runTest(ClientGameTestContext context) {
		try (TestSingleplayerContext world = context.worldBuilder().create()) {
			world.getConnection().waitForChunksRender();
			world.getServer().runCommand("time set noon");
			world.getServer().runCommand("weather clear");
			context.getInput().lookAt(0f, 5f);
			context.waitTicks(20);

			// Wait (max 2 minutes) for the brain script to connect and spawn its NPC.
			world.getServer().waitFor(server -> {
				NpcManager npcs = McEca.npcs();
				return npcs != null && npcs.all().stream().anyMatch(n -> n.brainCount() > 0);
			}, 20 * 120);
			context.waitTicks(30);
			context.takeScreenshot("mceca-01-spawned");

			String steps = env("MCECA_TEST_STEPS", "");
			if (steps.isBlank()) {
				runMessages(context);
			} else {
				runSteps(context, world, steps);
			}

			for (NpcController npc : world.getServer().computeOnServer(server -> McEca.npcs().all())) {
				McEca.LOGGER.info("[gametest] NPC {} brains={}", npc.name(), npc.brainCount());
			}
			// The in-game helper commands (their output ends up in the log).
			world.getServer().runCommand("eca status");
			world.getServer().runCommand("eca list");
		}
	}

	private void runMessages(ClientGameTestContext context) {
		String[] messages = env("MCECA_TEST_MESSAGES", "Hello Ava!|Can you nod?|Bye!").split("\\|");
		int replyTicks = Integer.parseInt(env("MCECA_TEST_REPLY_TICKS", "120"));
		int i = 2;
		for (String message : messages) {
			context.runOnClient(mc -> mc.player.connection.sendChat(message));
			context.waitTicks(12);
			context.takeScreenshot(String.format("mceca-%02d-said-%s", i++, slug(message)));
			context.waitTicks(replyTicks / 2);
			context.takeScreenshot(String.format("mceca-%02d-reply", i++));
			context.waitTicks(replyTicks / 2);
		}
	}

	private void runSteps(ClientGameTestContext context, TestSingleplayerContext world, String steps) {
		int shot = 2;
		for (String step : steps.split("\\|")) {
			String kind = step.contains(":") ? step.substring(0, step.indexOf(':')) : step;
			String arg = step.contains(":") ? step.substring(step.indexOf(':') + 1) : "";
			McEca.LOGGER.info("[gametest] step {}", step);
			switch (kind.strip()) {
				case "chat" -> context.runOnClient(mc -> mc.player.connection.sendChat(arg));
				case "wait" -> context.waitTicks(Integer.parseInt(arg.strip()));
				case "shot" -> context.takeScreenshot(String.format("mceca-%02d-%s", shot++, slug(arg)));
				case "cmd" -> world.getServer().runCommand(arg);
				case "use" -> context.getInput().pressKey(options -> options.keyUse);
				case "attack" -> context.getInput().pressKey(options -> options.keyAttack);
				case "walk" -> context.getInput().holdKeyFor(options -> options.keyUp, Integer.parseInt(arg.strip()));
				case "look" -> {
					String[] yp = arg.split(",");
					context.getInput().lookAt(Float.parseFloat(yp[0]), Float.parseFloat(yp[1]));
				}
				case "aim" -> context.runOnClient(mc -> {
					var player = mc.player;
					var npc = mc.level.getEntitiesOfClass(Mannequin.class, player.getBoundingBox().inflate(32)).stream()
							.min(Comparator.comparingDouble(e -> e.distanceToSqr(player))).orElse(null);
					if (npc == null) return;
					Vec3 from = player.getEyePosition();
					Vec3 to = npc.position().add(0, npc.getBbHeight() * 0.6, 0);
					double dx = to.x - from.x, dy = to.y - from.y, dz = to.z - from.z;
					player.setYRot((float) (Math.toDegrees(Math.atan2(dz, dx)) - 90));
					player.setXRot((float) -Math.toDegrees(Math.atan2(dy, Math.sqrt(dx * dx + dz * dz))));
				});
				case "talk_start" -> context.getInput().holdKey(InputConstants.KEY_V);
				case "talk_end" -> context.getInput().releaseKey(InputConstants.KEY_V);
				default -> throw new IllegalArgumentException("unknown test step: " + step);
			}
		}
	}

	private static String env(String key, String fallback) {
		String value = System.getenv(key);
		return value == null || value.isBlank() ? fallback : value;
	}

	private static String slug(String s) {
		String slug = s.toLowerCase().replaceAll("[^a-z0-9]+", "-").replaceAll("(^-|-$)", "");
		return slug.length() > 20 ? slug.substring(0, 20) : slug;
	}
}
