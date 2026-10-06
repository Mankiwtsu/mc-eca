package io.github.mceca.client;

import com.mojang.blaze3d.platform.InputConstants;
import io.github.mceca.voice.PushToTalkPayload;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayNetworking;
import net.minecraft.client.KeyMapping;
import net.minecraft.resources.Identifier;

/**
 * Client part of MC-ECA: the push-to-talk key (default V, change it under Options ->
 * Controls -> Key Binds -> MC-ECA). Holding it near an NPC tells the brain script to
 * record your microphone; releasing it sends what you said.
 */
public class McEcaClient implements ClientModInitializer {
	private static final KeyMapping.Category CATEGORY = KeyMapping.Category.register(Identifier.fromNamespaceAndPath("mceca", "mceca"));
	private static KeyMapping talkKey;
	private static boolean wasDown;

	@Override
	public void onInitializeClient() {
		talkKey = KeyMappingHelper.registerKeyMapping(new KeyMapping("key.mceca.talk", InputConstants.KEY_V, CATEGORY));

		ClientTickEvents.END_CLIENT_TICK.register(client -> {
			// isDown() is false while a screen (chat, inventory) is open, so typing a "v" never triggers it.
			boolean down = client.player != null && talkKey.isDown();
			if (down != wasDown && ClientPlayNetworking.canSend(PushToTalkPayload.TYPE)) {
				ClientPlayNetworking.send(new PushToTalkPayload(down));
			}
			wasDown = down;
		});
	}
}
