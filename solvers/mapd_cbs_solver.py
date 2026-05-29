from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from env import DeliveryEnv, Order, Shipper, delivery_reward, valid_next_pos
from solvers.solver import Solver, INF, MOVES, Position, Move

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
        self._last_assign_t: int = -10**9
        self._bucket_size: int = max(8, self.N // 10)

    # ------------------------------------------------------------------
    # Layer 1: Task assignment
    # ------------------------------------------------------------------
    def _is_large_assignment(self, active_unpicked: int) -> bool:
        return self.N >= 50 or active_unpicked >= max(120, self.C * 8)

    def _candidate_k(self) -> int:
        if self.N >= 80:
            return 40
        if self.N >= 50:
            return 30
        return 20

    def _replan_interval(self) -> int:
        if self.N >= 80:
            return 4
        if self.N >= 50:
            return 3
        return 1

    def _bucket_key(self, pos: Position) -> Tuple[int, int]:
        return pos[0] // self._bucket_size, pos[1] // self._bucket_size

    def _valid_sticky(self, shippers: List[Shipper],
                      orders: Dict[int, Order]) -> Dict[int, int]:
        smap = {s.id: s for s in shippers}
        sticky: Dict[int, int] = {}
        for sid, oid in self._assignments.items():
            s = smap.get(sid)
            o = orders.get(oid)
            if s is None or o is None or o.picked or o.delivered:
                continue
            if len(s.bag) < s.K_max and s.can_carry(o, orders):
                sticky[sid] = oid
        return sticky

    def _cheap_pickup_score(self, s: Shipper, o: Order, t: int,
                            orders: Dict[int, Order]) -> float:
        if not s.can_carry(o, orders):
            return -INF
        d1 = abs(s.r - o.sx) + abs(s.c - o.sy)
        d2 = abs(o.sx - o.ex) + abs(o.sy - o.ey)
        total_d = d1 + d2
        arrival = t + total_d
        est_reward = delivery_reward(o, arrival, self.T)
        pw = {1: 1.0, 2: 2.5, 3: 5.0}[o.p]
        score = pw * est_reward / max(1, total_d)
        slack = o.et - arrival
        if slack >= 0:
            score += 3.0 / max(1, slack + 1)
        else:
            score *= {1: 0.2, 2: 0.4, 3: 0.6}[o.p]
        rel_d = d1 / max(1.0, self._map_radius)
        if rel_d > 1.5:
            score *= 0.4
        elif rel_d > 0.8:
            score *= 0.7
        hs = self._hotspot_counts.get((o.sx, o.sy), 0.0)
        if hs > 0:
            score += hs * max(0.01, abs(score) * 0.02)
        return score

    def _build_buckets(self, unpicked: List[Order]) -> Dict[Tuple[int, int], List[Order]]:
        buckets: Dict[Tuple[int, int], List[Order]] = {}
        for o in unpicked:
            buckets.setdefault(self._bucket_key((o.sx, o.sy)), []).append(o)
        return buckets

    def _hotspot_bucket_keys(self) -> List[Tuple[int, int]]:
        seen = set()
        result: List[Tuple[int, int]] = []
        for pos, _ in sorted(self._hotspot_counts.items(), key=lambda item: -item[1]):
            key = self._bucket_key(pos)
            if key not in seen:
                seen.add(key)
                result.append(key)
            if len(result) >= max(3, self.C // 4):
                break
        return result

    def _global_priority_orders(self, unpicked: List[Order], t: int,
                                limit: int) -> List[Order]:
        return sorted(
            unpicked,
            key=lambda o: (
                -{1: 1.0, 2: 2.5, 3: 5.0}[o.p],
                o.et,
                abs(o.sx - o.ex) + abs(o.sy - o.ey),
                o.id,
            ),
        )[:limit]

    def _candidate_orders_for_shipper(
        self,
        s: Shipper,
        unpicked: List[Order],
        buckets: Dict[Tuple[int, int], List[Order]],
        hotspot_keys: List[Tuple[int, int]],
        global_orders: List[Order],
        t: int,
        orders: Dict[int, Order],
    ) -> List[Tuple[float, int, int]]:
        candidate_k = self._candidate_k()
        cheap_limit = candidate_k * 3
        exact_limit = candidate_k
        pool: Dict[int, Order] = {}
        base_br, base_bc = self._bucket_key((s.r, s.c))

        for radius in (0, 1, 2):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if max(abs(dr), abs(dc)) != radius:
                        continue
                    for o in buckets.get((base_br + dr, base_bc + dc), []):
                        pool[o.id] = o
            if len(pool) >= cheap_limit:
                break

        for key in hotspot_keys:
            for o in buckets.get(key, []):
                pool[o.id] = o

        for o in global_orders:
            pool[o.id] = o

        cheap_scored: List[Tuple[float, Order]] = []
        for o in pool.values():
            sc = self._cheap_pickup_score(s, o, t, orders)
            if sc > -INF:
                cheap_scored.append((sc, o))
        cheap_scored.sort(key=lambda item: (-item[0], item[1].id))

        exact: List[Tuple[float, int, int]] = []
        for _, o in cheap_scored[:exact_limit]:
            sc = self.score_pickup(s, o, t, orders)
            if sc > -INF:
                exact.append((sc, s.id, o.id))
        exact.sort(key=lambda item: (-item[0], item[2]))
        return exact[:candidate_k]

    def _assign_large(self, t: int, orders: Dict[int, Order],
                      shippers: List[Shipper], sticky: Dict[int, int],
                      unpicked: List[Order]) -> Dict[int, int]:
        buckets = self._build_buckets(unpicked)
        hotspot_keys = self._hotspot_bucket_keys()
        global_orders = self._global_priority_orders(
            unpicked, t, max(self._candidate_k(), self.C * 2)
        )
        sticky_orders = set(sticky.values())
        scores: List[Tuple[float, int, int]] = []
        for s in shippers:
            if len(s.bag) >= s.K_max or s.id in sticky:
                continue
            for sc, sid, oid in self._candidate_orders_for_shipper(
                s, unpicked, buckets, hotspot_keys, global_orders, t, orders
            ):
                if oid not in sticky_orders:
                    scores.append((sc, sid, oid))

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
        return new_assign

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

        unpicked = [o for o in orders.values() if not o.picked and not o.delivered]
        large_assignment = self._is_large_assignment(len(unpicked))
        use_sticky_assignment = self.N >= 20 or self.C > self.N
        sticky = self._valid_sticky(shippers, orders) if use_sticky_assignment else {}

        if large_assignment:
            idle_without_assignment = any(
                not s.bag and len(s.bag) < s.K_max and s.id not in sticky
                for s in shippers
            )
            force_replan = (
                (not sticky and bool(unpicked))
                or (len(obs.get("new_order_ids", [])) >= max(3, self.C // 3))
                or (idle_without_assignment and bool(unpicked))
            )
            due_replan = t - self._last_assign_t >= self._replan_interval()
            if not force_replan and not due_replan:
                self._assignments = sticky
                return
            self._assignments = self._assign_large(t, orders, shippers, sticky, unpicked)
            self._last_assign_t = t
            return

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
        self._last_assign_t = t

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
    def _next_move(self, start: Position, target: Position) -> Move:
        if self.N >= 50:
            return self.bfs_next_move_from_goal(start, target)
        return self.bfs_next_move(start, target)

    def _wander_target(self, shipper: Shipper, orders: Dict[int, Order]) -> Position:
        if self.N < 50:
            return self.smart_wander_target(shipper, orders)
        pos = (shipper.r, shipper.c)
        best_score = -1.0
        best_target = self._wander_fallback
        for p, count in self._hotspot_counts.items():
            d = abs(pos[0] - p[0]) + abs(pos[1] - p[1])
            score = count / max(1, d)
            if score > best_score:
                best_score = score
                best_target = p
        if best_score >= 0:
            return best_target
        pending: Dict[Position, int] = {}
        for o in orders.values():
            if not o.picked and not o.delivered:
                p = (o.sx, o.sy)
                pending[p] = pending.get(p, 0) + 1
        for p, count in pending.items():
            d = abs(pos[0] - p[0]) + abs(pos[1] - p[1])
            score = count / max(1, d)
            if score > best_score:
                best_score = score
                best_target = p
        return best_target

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
                wander = self._wander_target(s, orders)
                mv = self._next_move(pos, wander)
                nxt = valid_next_pos(pos, mv, self.grid)
                if nxt in reserved:
                    mv = "S"
                    nxt = pos
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                reserved[nxt] = s.id
                continue

            mv = self._next_move(pos, target)
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
