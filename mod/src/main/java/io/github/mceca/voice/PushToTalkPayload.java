package io.github.mceca.voice;

import net.minecraft.network.RegistryFriendlyByteBuf;
import net.minecraft.network.codec.ByteBufCodecs;
import net.minecraft.network.codec.StreamCodec;
import net.minecraft.network.protocol.common.custom.CustomPacketPayload;
import net.minecraft.resources.Identifier;

/**
 * Client -> server: the player pressed (true) or released (false) the push-to-talk key.
 * The audio itself never goes through Minecraft: the brain script records the microphone
 * on the same computer.
 */
public record PushToTalkPayload(boolean pressed) implements CustomPacketPayload {
	public static final Type<PushToTalkPayload> TYPE = new Type<>(Identifier.fromNamespaceAndPath("mceca", "push_to_talk"));
	public static final StreamCodec<RegistryFriendlyByteBuf, PushToTalkPayload> CODEC =
			StreamCodec.composite(ByteBufCodecs.BOOL, PushToTalkPayload::pressed, PushToTalkPayload::new);

	@Override
	public Type<? extends CustomPacketPayload> type() {
		return TYPE;
	}
}
