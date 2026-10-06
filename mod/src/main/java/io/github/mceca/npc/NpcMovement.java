package io.github.mceca.npc;

import io.github.mceca.McEca;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.util.Mth;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.level.pathfinder.Path;
import net.minecraft.world.phys.Vec3;

/**
 * Walking for an NPC body.
 *
 * Mannequins have no AI, so they can't find a way by themselves. We borrow Minecraft's
 * pathfinder: a hidden helper mob (never added to the world) computes a path from the
 * NPC to the goal, and the mannequin walks it node by node, jumping up one-block steps.
 * If no path is found it walks in a straight line.
 */
class NpcMovement {
	enum Mode { NONE, WALK_TO_POS, WALK_TO_PLAYER, FOLLOW }

	enum Result { NONE, ARRIVED, STUCK }

	/** Blocks per tick at speed 1.0 (a calm walk; players walk at ~0.22). */
	private static final double WALK_SPEED = 0.17;
	private static final float MAX_TURN = 25f;
	private static final int STUCK_CHECK_TICKS = 40;

	private Mode mode = Mode.NONE;
	private Vec3 targetPos;
	private ServerPlayer targetPlayer;
	private double distance;
	private double speed = 1.0;

	private Path path;
	private int repathIn;
	private Vec3 pathGoal;
	private Mob pathHelper;

	private boolean moving;
	private float moveYaw;
	private int stuckTimer;
	private double lastGoalDistance;
	private int stuckStrikes;
	private boolean stuckReported;

	void walkTo(Vec3 pos, double distance, double speed) {
		start(Mode.WALK_TO_POS, distance, speed);
		this.targetPos = pos;
	}

	void walkTo(ServerPlayer player, double distance, double speed) {
		start(Mode.WALK_TO_PLAYER, distance, speed);
		this.targetPlayer = player;
	}

	void follow(ServerPlayer player, double distance, double speed) {
		start(Mode.FOLLOW, distance, speed);
		this.targetPlayer = player;
	}

	void stop(Mannequin body) {
		mode = Mode.NONE;
		targetPlayer = null;
		targetPos = null;
		path = null;
		if (body != null && moving) halt(body);
		moving = false;
	}

	private void start(Mode mode, double distance, double speed) {
		this.mode = mode;
		this.distance = Math.max(0.3, distance);
		this.speed = Mth.clamp(speed, 0.2, 3.0);
		this.targetPlayer = null;
		this.targetPos = null;
		this.path = null;
		this.repathIn = 0;
		this.stuckTimer = 0;
		this.stuckStrikes = 0;
		this.stuckReported = false;
		this.lastGoalDistance = Double.MAX_VALUE;
	}

	boolean isMoving() {
		return moving;
	}

	boolean isActive() {
		return mode != Mode.NONE;
	}

	float moveYaw() {
		return moveYaw;
	}

	/** Runs every tick. Returns ARRIVED/STUCK once when that happens. */
	Result tick(Mannequin body, float currentYaw) {
		boolean wasMoving = moving;
		moving = false;
		if (mode == Mode.NONE) return Result.NONE;

		Vec3 goal;
		if (mode == Mode.WALK_TO_POS) {
			goal = targetPos;
		} else {
			if (targetPlayer == null || targetPlayer.isRemoved() || targetPlayer.level() != body.level()) {
				stop(body);
				return Result.STUCK;
			}
			goal = targetPlayer.position();
		}

		Vec3 pos = body.position();
		double goalDistance = pos.distanceTo(goal);
		if (goalDistance <= distance) {
			halt(body);
			path = null;
			stuckTimer = 0;
			stuckStrikes = 0;
			if (mode == Mode.FOLLOW) {
				stuckReported = false;
				return Result.NONE; // wait here until the player moves away again
			}
			mode = Mode.NONE;
			return Result.ARRIVED;
		}
		// Following: don't twitch for tiny movements of the player.
		if (mode == Mode.FOLLOW && !wasMoving && goalDistance <= distance + 0.75) {
			return Result.NONE;
		}

		// (Re)compute the path now and then, or when a moving target went elsewhere.
		if (path == null || --repathIn <= 0 || (pathGoal != null && pathGoal.distanceTo(goal) > 2.0)) {
			path = findPath((ServerLevel) body.level(), pos, goal);
			pathGoal = goal;
			repathIn = mode == Mode.WALK_TO_POS ? 60 : 20;
		}

		Vec3 waypoint = nextWaypoint(body, goal);
		Vec3 delta = new Vec3(waypoint.x - pos.x, 0, waypoint.z - pos.z);
		double horizontal = delta.length();
		Vec3 velocity = body.getDeltaMovement();
		if (horizontal > 1.0E-3) {
			Vec3 dir = delta.scale(1.0 / horizontal);
			double step = Math.min(WALK_SPEED * speed, horizontal);
			float targetYaw = (float) (Mth.atan2(dir.z, dir.x) * Mth.RAD_TO_DEG) - 90f;
			moveYaw = currentYaw + Mth.clamp(Mth.wrapDegrees(targetYaw - currentYaw), -MAX_TURN, MAX_TURN);
			double vy = velocity.y;
			boolean stepUp = waypoint.y > pos.y + 0.5 || body.horizontalCollision;
			if (stepUp && body.onGround()) vy = 0.42;
			body.setDeltaMovement(dir.x * step, vy, dir.z * step);
			moving = true;
		}

		// Stuck detection: no real progress for a few seconds.
		if (++stuckTimer >= STUCK_CHECK_TICKS) {
			stuckTimer = 0;
			if (lastGoalDistance - goalDistance < 0.5) {
				stuckStrikes++;
				path = null; // try a fresh path
			} else {
				stuckStrikes = 0;
			}
			lastGoalDistance = goalDistance;
			if (stuckStrikes >= 3) {
				if (mode != Mode.FOLLOW) {
					stop(body);
					return Result.STUCK;
				}
				// Following: report once, keep trying.
				stuckStrikes = 0;
				if (!stuckReported) {
					stuckReported = true;
					return Result.STUCK;
				}
			}
		}
		return Result.NONE;
	}

	private Vec3 nextWaypoint(Mannequin body, Vec3 goal) {
		if (path == null) return goal;
		Vec3 pos = body.position();
		while (!path.isDone()) {
			BlockPos node = path.getNextNodePos();
			Vec3 center = new Vec3(node.getX() + 0.5, node.getY(), node.getZ() + 0.5);
			double dx = center.x - pos.x, dz = center.z - pos.z;
			if (dx * dx + dz * dz < 0.35 * 0.35 && Math.abs(center.y - pos.y) < 1.0) {
				path.advance();
			} else {
				return center;
			}
		}
		return goal;
	}

	private Path findPath(ServerLevel level, Vec3 from, Vec3 goal) {
		try {
			if (pathHelper == null || pathHelper.level() != level) {
				pathHelper = EntityTypes.ZOMBIE.create(level, EntitySpawnReason.COMMAND);
				if (pathHelper == null) return null;
				var range = pathHelper.getAttribute(Attributes.FOLLOW_RANGE);
				if (range != null) range.setBaseValue(64.0);
			}
			pathHelper.snapTo(from.x, from.y, from.z, 0f, 0f);
			pathHelper.setOnGround(true);
			pathHelper.getNavigation().stop();
			int accuracy = mode == Mode.WALK_TO_POS ? 0 : 1;
			Path p = pathHelper.getNavigation().createPath(BlockPos.containing(goal), accuracy);
			return p == null || p.getNodeCount() == 0 ? null : p;
		} catch (RuntimeException e) {
			McEca.LOGGER.debug("MC-ECA pathfinding failed: {}", e.toString());
			return null;
		}
	}

	private static void halt(Mannequin body) {
		Vec3 v = body.getDeltaMovement();
		body.setDeltaMovement(0, v.y, 0);
	}
}
