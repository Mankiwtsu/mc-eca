package io.github.mceca.npc;

import io.github.mceca.bridge.CommandException;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

import java.util.Locale;

/** Converts between item names used in the protocol ("apple", "minecraft:apple") and items. */
final class ItemNames {
	private ItemNames() {
	}

	static Item parse(String name) throws CommandException {
		String clean = name.strip().toLowerCase(Locale.ROOT).replace(' ', '_');
		Identifier id = Identifier.tryParse(clean.contains(":") ? clean : "minecraft:" + clean);
		if (id == null || !BuiltInRegistries.ITEM.containsKey(id)) {
			throw new CommandException("unknown item '" + name + "' (use Minecraft item names like apple, diamond, oak_log)");
		}
		Item item = BuiltInRegistries.ITEM.getValue(id);
		if (item == Items.AIR) throw new CommandException("unknown item '" + name + "'");
		return item;
	}

	/** "apple" for vanilla items, "mod:thing" for others, null for an empty stack. */
	static String name(ItemStack stack) {
		if (stack == null || stack.isEmpty()) return null;
		Identifier id = BuiltInRegistries.ITEM.getKey(stack.getItem());
		return id.getNamespace().equals("minecraft") ? id.getPath() : id.toString();
	}
}
