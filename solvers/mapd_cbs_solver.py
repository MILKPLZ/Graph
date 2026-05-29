from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from env import DeliveryEnv, Order, Shipper, valid_next_pos
from solvers_v1.solver import Solver, INF, MOVES, Position, Move

Action = Tuple[Move, object]


class MAPDCBSSolver(Solver):
    """
    MAPD-CBS V5 — Conflict-Based Search lite.
    Layer 1: Score-based global task assignment (re-plan every step)
    Layer 2: Priority-ordered path planning with reservation table + edge-swap check
    """

    method_name = "MAPDCBSSolver"

    def __init__(self, env: DeliveryEnv):
        super().__init__(env)
        self._assignments: Dict[int, int] = {}
        self._delivery_targets: Dict[int, Position] = {}
        self._wait_count: Dict[int, int] = {}
        self._last_pos: Dict[int, Position] = {}

    # ------------------------------------------------------------------
    # Layer 1: Task assignment
    # ------------------------------------------------------------------
    def _task_assign(self, obs: dict):
        t = obs["t"]
        orders = obs["orders"]
        shippers = obs["shippers"]
        self.update_hotspot(obs.get("new_order_ids", []), orders)

        for s in shippers:
            if s.bag:
                dest = self.best_delivery_dest(s, orders, t)
                if dest:
                    self._delivery_targets[s.id] = dest
                else:
                    self._delivery_targets.pop(s.id, None)
            else:
                self._delivery_targets.pop(s.id, None)

        use_sticky_assignment = self.N >= 20 or self.C > self.N
        smap = {s.id: s for s in shippers}
        sticky: Dict[int, int] = {}
        if use_sticky_assignment:
            for sid, oid in self._assignments.items():
                s = smap.get(sid)
                o = orders.get(oid)
                if s is None or o is None or o.picked or o.delivered:
                    continue
                if len(s.bag) < s.K_max and s.can_carry(o, orders):
                    sticky[sid] = oid

        unpicked = [o for o in orders.values() if not o.picked and not o.delivered]
        scores: List[Tuple[float, int, int]] = []
        sticky_orders = set(sticky.values())
        for s in shippers:
            if len(s.bag) >= s.K_max or s.id in sticky:
                continue
            for o in unpicked:
                if o.id in sticky_orders:
                    continue
                sc = self.score_pickup(s, o, t, orders)
                if sc > -INF:
                    scores.append((sc, s.id, o.id))

        scores.sort(key=lambda x: -x[0])
        used_s: set = set(sticky)
        used_o: set = set(sticky.values())
        new_assign: Dict[int, int] = dict(sticky)
        for sc, sid, oid in scores:
            if sid in used_s or oid in used_o:
                continue
            new_assign[sid] = oid
            used_s.add(sid)
            used_o.add(oid)

        self._assignments = new_assign

    # ------------------------------------------------------------------
    # CBS-specific urgency threshold: less aggressive on large maps
    # to allow batching before forcing delivery mode
    # ------------------------------------------------------------------
    def urgent_slack_threshold(self, bag_count: int = 0, k_max: int = 1) -> int:
        avg_cross = self.N * 0.7
        urgency_multiplier = 1.3 if self.N >= 20 else 1.5
        base = max(3, int(avg_cross * urgency_multiplier))
        if k_max > 0 and bag_count > 0:
            fill = bag_count / k_max
            if fill >= 1.0:
                return 999
            elif fill >= 0.75:
                return max(3, base - int(avg_cross * 0.3))
            elif fill >= 0.5:
                return max(3, base - int(avg_cross * 0.1))
        return base

    # ------------------------------------------------------------------
    # Priority scoring
    # ------------------------------------------------------------------
    def _shipper_urgency(self, s: Shipper, orders: Dict[int, Order], t: int) -> float:
        urgency = 0.0
        for oid in s.bag:
            if oid in orders and not orders[oid].delivered:
                slack = orders[oid].et - t
                t_scale = max(1, self.T // 240) if (self.N >= 20 or self.C > self.N) else 1
                urgency = max(urgency, 100.0 * t_scale / max(1, slack))
                urgency += {1: 0, 2: 1, 3: 3}[orders[oid].p]
        if s.id in self._assignments and self._assignments[s.id] in orders:
            o = orders[self._assignments[s.id]]
            urgency += {1: 0, 2: 1, 3: 2}[o.p]
        return urgency

    def _get_target(self, s: Shipper, orders: Dict[int, Order], t: int) -> Optional[Position]:
        pos = (s.r, s.c)
        # Immediate delivery
        for oid in s.bag:
            if oid in orders and not orders[oid].delivered:
                if (orders[oid].ex, orders[oid].ey) == pos:
                    return pos

        # Urgency check
        has_urgent = False
        if s.bag:
            threshold = self.urgent_slack_threshold(len(s.bag), s.K_max)
            for oid in s.bag:
                if oid in orders and not orders[oid].delivered:
                    o = orders[oid]
                    d = self.bfs_distance(pos, (o.ex, o.ey))
                    if d < INF and o.et - (t + d) < threshold:
                        has_urgent = True
                        break

        if has_urgent and s.id in self._delivery_targets:
            return self._delivery_targets[s.id]

        # Pickup
        if s.id in self._assignments and len(s.bag) < s.K_max:
            oid = self._assignments[s.id]
            if oid in orders and not orders[oid].picked:
                return (orders[oid].sx, orders[oid].sy)

        # Non-urgent delivery
        if s.bag and s.id in self._delivery_targets:
            return self._delivery_targets[s.id]

        return None

    # ------------------------------------------------------------------
    # Layer 2: Priority-based conflict resolution
    # ------------------------------------------------------------------
    def _decide_actions(self, obs: dict) -> Dict[int, Action]:
        t = obs["t"]
        orders = obs["orders"]
        shippers = obs["shippers"]

        sorted_shippers = sorted(shippers, key=lambda s: -self._shipper_urgency(s, orders, t))
        reserved: Dict[Position, int] = {}
        current_cells: Dict[int, Position] = {s.id: (s.r, s.c) for s in shippers}
        actions: Dict[int, Action] = {}

        for s in sorted_shippers:
            pos = (s.r, s.c)

            can_deliver = any(
                oid in orders and not orders[oid].delivered
                and (orders[oid].ex, orders[oid].ey) == pos
                for oid in s.bag
            )
            if can_deliver:
                actions[s.id] = ("S", 2)
                reserved[pos] = s.id
                continue

            target = self._get_target(s, orders, t)
            if target is None:
                wander = self.smart_wander_target(s, orders)
                mv = self.bfs_next_move(pos, wander)
                nxt = valid_next_pos(pos, mv, self.grid)
                if nxt in reserved:
                    mv = "S"
                    nxt = pos
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                reserved[nxt] = s.id
                continue

            mv = self.bfs_next_move(pos, target)
            nxt = valid_next_pos(pos, mv, self.grid)

            # Conflict resolution: pick best alternative
            if nxt != pos and nxt in reserved:
                found_alt = False
                best_alt_mv = "S"
                best_alt_d = INF
                for alt_mv in MOVES:
                    alt_nxt = valid_next_pos(pos, alt_mv, self.grid)
                    if alt_nxt != pos and alt_nxt not in reserved:
                        d_alt = self.bfs_distance(alt_nxt, target)
                        if d_alt < best_alt_d:
                            best_alt_d = d_alt
                            best_alt_mv = alt_mv
                            found_alt = True
                if found_alt:
                    d_orig = self.bfs_distance(pos, target)
                    use_wide_alt = self.N >= 20 or self.C > self.N
                    alt_tol = max(4, self.N // 5) if use_wide_alt else max(2, self.N // 8)
                    if best_alt_d <= d_orig + alt_tol:
                        mv = best_alt_mv
                        nxt = valid_next_pos(pos, mv, self.grid)
                    else:
                        mv = "S"
                        nxt = pos
                else:
                    mv = "S"
                    nxt = pos

            # Edge swap check
            if nxt != pos:
                for other_sid, other_pos in current_cells.items():
                    if other_sid == s.id:
                        continue
                    if other_pos == nxt and other_sid in actions:
                        other_mv = actions[other_sid][0]
                        other_nxt = valid_next_pos(other_pos, other_mv, self.grid)
                        if other_nxt == pos:
                            mv = "S"
                            nxt = pos
                            break

            # Deadlock detection: force a random valid move after 3 consecutive waits
            use_deadlock_escape = self.N >= 20 or self.C > self.N
            if use_deadlock_escape and mv == "S" and can_deliver is False:
                self._wait_count[s.id] = self._wait_count.get(s.id, 0) + 1
                if self._wait_count[s.id] >= 3 and target is not None:
                    for forced_mv in MOVES:
                        forced_nxt = valid_next_pos(pos, forced_mv, self.grid)
                        if forced_nxt != pos and forced_nxt not in reserved:
                            mv = forced_mv
                            nxt = forced_nxt
                            self._wait_count[s.id] = 0
                            break
            else:
                self._wait_count[s.id] = 0

            op = self.choose_cargo_op(s, nxt, orders)
            actions[s.id] = (mv, op)
            reserved[nxt] = s.id

        return actions

    def run(self) -> dict:
        start_time = time.time()
        obs = self.env.reset()
        while not obs.get("done", False):
            self._task_assign(obs)
            actions = self._decide_actions(obs)
            obs, _, done, _ = self.env.step(actions)
            if done:
                break
        return self.env.result(self.method_name, elapsed_sec=time.time() - start_time)
