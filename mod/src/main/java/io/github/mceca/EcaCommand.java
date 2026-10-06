package io.github.mceca;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import io.github.mceca.bridge.Bridge;
import io.github.mceca.npc.NpcController;
import io.github.mceca.npc.NpcManager;
import net.minecraft.ChatFormatting;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;

/**
 * In-game helper commands:
 * <pre>
 *   /eca status          is the bridge running, how many scripts are connected
 *   /eca list            all NPCs and whether a brain is connected
 *   /eca remove NAME     delete an NPC
 * </pre>
 */
final class EcaCommand {
	private EcaCommand() {
	}

	static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
		dispatcher.register(Commands.literal("eca")
				.then(Commands.literal("status").executes(ctx -> {
					Bridge bridge = McEca.bridge();
					String msg;
					if (bridge == null) {
						msg = "MC-ECA is not running";
					} else if (bridge.failure() != null) {
						msg = "MC-ECA bridge failed: " + bridge.failure();
					} else {
						msg = "MC-ECA listening on " + bridge.bindAddress() + ":" + bridge.port() + ", " + bridge.clientCount() + " script(s) connected";
					}
					ctx.getSource().sendSystemMessage(Component.literal(msg));
					return 1;
				}))
				.then(Commands.literal("list").executes(ctx -> {
					NpcManager npcs = McEca.npcs();
					if (npcs == null || npcs.all().isEmpty()) {
						ctx.getSource().sendSystemMessage(Component.literal("No NPCs yet. Start a script to spawn one."));
						return 0;
					}
					for (NpcController npc : npcs.all()) {
						boolean brain = npc.brainCount() > 0;
						ctx.getSource().sendSystemMessage(Component.literal("- " + npc.name() + "  ")
								.append(Component.literal(brain ? "connected" : "no brain")
										.withStyle(brain ? ChatFormatting.GREEN : ChatFormatting.GRAY)));
					}
					return 1;
				}))
				.then(Commands.literal("remove")
						.then(Commands.argument("name", StringArgumentType.word()).executes(ctx -> {
							String name = StringArgumentType.getString(ctx, "name");
							NpcManager npcs = McEca.npcs();
							boolean removed = npcs != null && npcs.removeByName(name);
							ctx.getSource().sendSystemMessage(Component.literal(removed ? "Removed " + name : "No NPC named " + name + " nearby"));
							return removed ? 1 : 0;
						}))));
	}
}
