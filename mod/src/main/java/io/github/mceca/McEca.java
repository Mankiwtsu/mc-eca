package io.github.mceca;

import io.github.mceca.bridge.Bridge;
import io.github.mceca.npc.NpcManager;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerEntityEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.event.player.AttackEntityCallback;
import net.fabricmc.fabric.api.event.player.UseEntityCallback;
import net.fabricmc.fabric.api.message.v1.ServerMessageEvents;
import net.fabricmc.fabric.api.networking.v1.PayloadTypeRegistry;
import net.fabricmc.fabric.api.networking.v1.ServerPlayNetworking;
import io.github.mceca.voice.PushToTalkPayload;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * MC-ECA entry point.
 *
 * The mod is the NPC's *body*: it spawns the character, moves its head, shows speech
 * bubbles and reports what players say. The *brain* runs outside Minecraft (e.g. a
 * Python script) and talks to the mod over a local socket, see {@link Bridge}.
 */
public class McEca implements ModInitializer {
	public static final String MOD_ID = "mceca";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	private static NpcManager npcs;
	private static Bridge bridge;

	@Override
	public void onInitialize() {
		Config config = Config.load();

		ServerLifecycleEvents.SERVER_STARTED.register(server -> {
			npcs = new NpcManager(server, config);
			bridge = new Bridge(server, npcs, config.bind_address, config.port);
			bridge.start();
		});

		ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
			if (bridge != null) bridge.stop();
			// Remove speech bubbles before the world is saved, so none are left behind.
			if (npcs != null) npcs.shutdown();
			bridge = null;
			npcs = null;
		});

		ServerTickEvents.END_SERVER_TICK.register(server -> {
			if (npcs != null) npcs.tick();
		});

		ServerMessageEvents.CHAT_MESSAGE.register((message, sender, params) -> {
			if (npcs != null) npcs.onPlayerChat(sender, message.signedContent());
		});

		ServerEntityEvents.ENTITY_LOAD.register((entity, level) -> {
			if (npcs != null) npcs.onEntityLoad(entity);
		});

		// Push-to-talk (voice): the client mod sends key presses, the brain records the mic.
		PayloadTypeRegistry.serverboundPlay().register(PushToTalkPayload.TYPE, PushToTalkPayload.CODEC);
		ServerPlayNetworking.registerGlobalReceiver(PushToTalkPayload.TYPE, (payload, context) ->
				context.server().execute(() -> {
					if (npcs != null) npcs.onPushToTalk(context.player(), payload.pressed());
				}));

		// Right-click / punch on an NPC -> "click" / "hit" events for the brain.
		UseEntityCallback.EVENT.register((player, level, hand, entity, hit) -> {
			if (level.isClientSide() || hand != InteractionHand.MAIN_HAND || npcs == null) return InteractionResult.PASS;
			return npcs.onPlayerInteract((ServerPlayer) player, entity, false) ? InteractionResult.SUCCESS : InteractionResult.PASS;
		});
		AttackEntityCallback.EVENT.register((player, level, hand, entity, hit) -> {
			if (level.isClientSide() || npcs == null) return InteractionResult.PASS;
			return npcs.onPlayerInteract((ServerPlayer) player, entity, true) ? InteractionResult.SUCCESS : InteractionResult.PASS;
		});

		CommandRegistrationCallback.EVENT.register((dispatcher, registryAccess, environment) ->
				EcaCommand.register(dispatcher));

		LOGGER.info("MC-ECA loaded (bridge port {})", config.port);
	}

	public static NpcManager npcs() {
		return npcs;
	}

	public static Bridge bridge() {
		return bridge;
	}
}
