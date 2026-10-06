package io.github.mceca.bridge;

/** A command the brain sent could not be carried out; the message goes back to the brain. */
public class CommandException extends Exception {
	public CommandException(String message) {
		super(message);
	}
}
