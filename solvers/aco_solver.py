from __future__ import annotations

import random
import time
from typing import Dict, List, Optional, Tuple

from env import DeliveryEnv, Order, Shipper, valid_next_pos, delivery_reward
from solvers.solver import Solver, INF, MOVES, Position, Move

Action = Tuple[Move, object]


class ACOSolver(Solver):
    """
    ACO V5 — Ant Colony Optimization with adaptive parameters.
    - Greedy baseline every step, ACO exploration periodically
    - Pheromone guides ant exploration toward proven-good pairings
    - All params scale with N, G, C
    """

    method_name = "ACOSolver"

    def __init__(self, env: DeliveryEnv):
        super().__init__(env)
        # Order-level pheromone for small/medium maps (cross-shipper info sharing)
        # For large maze maps (N>=50), per-(shipper,order) to avoid congestion from convergence
        self._pheromone_shared = self.N < 50
        self._pheromone: Dict = {}
        self._delivery_targets: Dict[int, Position] = {}
        self._assignments: Dict[int, int] = {}
        self._last_plan_t: int = -10**9
        self._bucket_size: int = max(8, self.N // 10)
        large_or_dense = self.N > 20 or self.C > self.N
        seed = 42 + self.N * 97 + self.G * 13 + self.C * 7 if large_or_dense else 42
        self._rng = random.Random(seed)
        self._step_counter = 0

        # Adaptive ACO params
        self._aco_interval = max(2, self.N // 5)
        self._num_ants = max(4, min(12, self.G // max(1, self.C * 5)))
        self._num_iter = max(2, min(5, 200 // max(1, self.G)))
        self._candidate_k = max(10, min(30, self.G // 10)) if large_or_dense else max(15, self.G // 5)
        self._rho = 0.2

    def _is_large_assignment(self, active_unpicked: int) -> bool:
        return self.N >= 50 or active_unpicked >= max(120, self.C * 8)

    def _large_candidate_k(self) -> int:
        if self.N >= 80:
            return 40
        if self.N >= 50:
            return 30
        return 20

    def _large_replan_interval(self) -> int:
        if self.N >= 80:
            return 12
        if self.N >= 50:
            return 8
        return 4

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
        result: List[Tuple[int, int]] = []
        seen = set()
        for pos, _ in sorted(self._hotspot_counts.items(), key=lambda item: -item[1]):
            key = self._bucket_key(pos)
            if key in seen:
                continue
            seen.add(key)
            result.append(key)
            if len(result) >= max(3, self.C // 4):
                break
        return result

    def _global_priority_orders(self, unpicked: List[Order], limit: int) -> List[Order]:
        return sorted(
            unpicked,
            key=lambda o: (
                -{1: 1.0, 2: 2.5, 3: 5.0}[o.p],
                o.et,
                abs(o.sx - o.ex) + abs(o.sy - o.ey),
                o.id,
            ),
        )[:limit]

    def _large_candidate_pool(
        self,
        s: Shipper,
        buckets: Dict[Tuple[int, int], List[Order]],
        hotspot_keys: List[Tuple[int, int]],
        global_orders: List[Order],
    ) -> Dict[int, Order]:
        candidate_k = self._large_candidate_k()
        cheap_limit = candidate_k * 3
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
        return pool

    def _large_score_matrix(
        self,
        free: List[Shipper],
        unpicked: List[Order],
        orders: Dict[int, Order],
        t: int,
    ) -> Tuple[Dict[int, Order], Dict[int, List[Tuple[float, int]]], Dict[Tuple[int, int], float]]:
        buckets = self._build_buckets(unpicked)
        hotspot_keys = self._hotspot_bucket_keys()
        global_orders = self._global_priority_orders(
            unpicked, max(self._large_candidate_k(), self.C * 2)
        )
        candidate_orders: Dict[int, Order] = {}
        by_shipper: Dict[int, List[Tuple[float, int]]] = {}
        score_map: Dict[Tuple[int, int], float] = {}
        exact_limit = self._large_candidate_k()
        cheap_limit = exact_limit * 3
        for s in free:
            pool = self._large_candidate_pool(s, buckets, hotspot_keys, global_orders)
            cheap_scored: List[Tuple[float, Order]] = []
            for o in pool.values():
                sc = self._cheap_pickup_score(s, o, t, orders)
                if sc > -INF:
                    cheap_scored.append((sc, o))
            cheap_scored.sort(key=lambda item: (-item[0], item[1].id))
            exact: List[Tuple[float, int]] = []
            for _, o in cheap_scored[:exact_limit]:
                sc = self.score_pickup(s, o, t, orders)
                if sc > -INF:
                    candidate_orders[o.id] = o
                    score_map[(s.id, o.id)] = sc
                    exact.append((sc, o.id))
            exact.sort(key=lambda item: (-item[0], item[1]))
            by_shipper[s.id] = exact[:exact_limit]
        return candidate_orders, by_shipper, score_map

    def _get_pheromone(self, sid: int, oid: int) -> float:
        key = oid if self._pheromone_shared else (sid, oid)
        return self._pheromone.get(key, 1.0)

    def _evaporate(self):
        for key in list(self._pheromone.keys()):
            self._pheromone[key] *= (1.0 - self._rho)
            if self._pheromone[key] < 0.01:
                del self._pheromone[key]

    def _deposit(self, assignment: Dict[int, int], quality: float):
        if quality <= 0:
            return
        dep = quality / max(1, len(assignment))
        for sid, oid in assignment.items():
            key = oid if self._pheromone_shared else (sid, oid)
            self._pheromone[key] = self._pheromone.get(key, 1.0) + dep

    def _order_utility(self, o: Order, free_shippers: List[Shipper], t: int) -> float:
        """Utility of an order relative to the nearest available shipper."""
        d2 = self.bfs_distance((o.sx, o.sy), (o.ex, o.ey))
        if d2 >= INF:
            return -INF
        min_d1 = INF
        for s in free_shippers:
            d1 = self.bfs_distance((s.r, s.c), (o.sx, o.sy))
            if d1 < min_d1:
                min_d1 = d1
        if min_d1 >= INF:
            return -INF
        est_reward = delivery_reward(o, t + min_d1 + d2, self.T)
        pw = {1: 1.0, 2: 2.5, 3: 5.0}[o.p]
        return pw * est_reward / max(1, min_d1 + d2)

    def _greedy_assign(self, shippers: List[Shipper],
                       orders: Dict[int, Order], t: int) -> Dict[int, int]:
        unpicked = [o for o in orders.values() if not o.picked and not o.delivered]
        scores: List[Tuple[float, int, int]] = []
        for s in shippers:
            if len(s.bag) >= s.K_max:
                continue
            for o in unpicked:
                sc = self.score_pickup(s, o, t, orders)
                if sc > -INF:
                    scores.append((sc, s.id, o.id))
        scores.sort(key=lambda x: -x[0])
        used_s: set = set()
        used_o: set = set()
        result: Dict[int, int] = {}
        for sc, sid, oid in scores:
            if sid in used_s or oid in used_o:
                continue
            result[sid] = oid
            used_s.add(sid)
            used_o.add(oid)
        return result

    def _ant_construct(self, free_shippers: List[Shipper],
                       candidates: List[Order], t: int,
                       orders: Dict[int, Order]) -> Dict[int, int]:
        assignment: Dict[int, int] = {}
        used: set = set()
        shuffled = list(free_shippers)
        self._rng.shuffle(shuffled)
        for s in shuffled:
            available = [o for o in candidates
                         if o.id not in used
                         and s.can_carry(o, orders)
                         and self.bfs_distance((s.r, s.c), (o.sx, o.sy)) < INF]
            if not available:
                continue
            probs = []
            for o in available:
                tau = self._get_pheromone(s.id, o.id)
                eta = max(0.01, self.score_pickup(s, o, t, orders))
                probs.append(max((tau ** 1.0) * (eta ** 2.5), 1e-12))
            total = sum(probs)
            if total <= 0:
                continue
            r = self._rng.random() * total
            cumsum = 0.0
            chosen = len(available) - 1
            for i, p in enumerate(probs):
                cumsum += p
                if cumsum >= r:
                    chosen = i
                    break
            assignment[s.id] = available[chosen].id
            used.add(available[chosen].id)
        return assignment

    def _large_greedy_assign(
        self,
        free: List[Shipper],
        by_shipper: Dict[int, List[Tuple[float, int]]],
        sticky: Dict[int, int],
    ) -> Dict[int, int]:
        scores: List[Tuple[float, int, int]] = []
        sticky_orders = set(sticky.values())
        for s in free:
            if s.id in sticky:
                continue
            for sc, oid in by_shipper.get(s.id, []):
                if oid not in sticky_orders:
                    scores.append((sc, s.id, oid))
        scores.sort(key=lambda item: -item[0])
        assigned_s = set(sticky)
        assigned_o = set(sticky.values())
        result = dict(sticky)
        for sc, sid, oid in scores:
            if sid in assigned_s or oid in assigned_o:
                continue
            result[sid] = oid
            assigned_s.add(sid)
            assigned_o.add(oid)
        return result

    def _large_ant_construct(
        self,
        free: List[Shipper],
        by_shipper: Dict[int, List[Tuple[float, int]]],
        score_map: Dict[Tuple[int, int], float],
        sticky: Dict[int, int],
    ) -> Dict[int, int]:
        assignment = dict(sticky)
        used = set(sticky.values())
        shuffled = [s for s in free if s.id not in sticky]
        self._rng.shuffle(shuffled)
        for s in shuffled:
            available = [(sc, oid) for sc, oid in by_shipper.get(s.id, []) if oid not in used]
            if not available:
                continue
            probs = []
            for sc, oid in available:
                tau = self._get_pheromone(s.id, oid)
                eta = max(0.01, score_map.get((s.id, oid), sc))
                probs.append(max((tau ** 1.0) * (eta ** 2.5), 1e-12))
            total = sum(probs)
            if total <= 0:
                chosen_oid = available[0][1]
            else:
                r = self._rng.random() * total
                acc = 0.0
                chosen_oid = available[-1][1]
                for i, p in enumerate(probs):
                    acc += p
                    if acc >= r:
                        chosen_oid = available[i][1]
                        break
            assignment[s.id] = chosen_oid
            used.add(chosen_oid)
        return assignment

    def _large_evaluate(
        self,
        assignment: Dict[int, int],
        score_map: Dict[Tuple[int, int], float],
        shippers: List[Shipper],
        orders: Dict[int, Order],
        t: int,
    ) -> float:
        total = 0.0
        for sid, oid in assignment.items():
            total += max(0.0, score_map.get((sid, oid), 0.0))
        for s in shippers:
            pos = (s.r, s.c)
            for oid in s.bag:
                if oid in orders and not orders[oid].delivered:
                    o = orders[oid]
                    d = self.bfs_distance(pos, (o.ex, o.ey))
                    if d < INF:
                        total += delivery_reward(o, t + d, self.T)
        return total

    def _evaluate(self, assignment: Dict[int, int],
                  shippers: List[Shipper], orders: Dict[int, Order], t: int) -> float:
        total = 0.0
        smap = {s.id: s for s in shippers}
        for sid, oid in assignment.items():
            if oid not in orders or sid not in smap:
                continue
            s = smap[sid]
            o = orders[oid]
            d1 = self.bfs_distance((s.r, s.c), (o.sx, o.sy))
            d2 = self.bfs_distance((o.sx, o.sy), (o.ex, o.ey))
            if d1 >= INF or d2 >= INF:
                continue
            total += delivery_reward(o, t + d1 + d2, self.T)
        # Include reward from orders already in bag
        for s in shippers:
            pos = (s.r, s.c)
            for oid in s.bag:
                if oid in orders and not orders[oid].delivered:
                    o = orders[oid]
                    d = self.bfs_distance(pos, (o.ex, o.ey))
                    if d < INF:
                        total += delivery_reward(o, t + d, self.T)
        return total

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

    def _plan(self, obs: dict) -> Dict[int, int]:
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
        if large_assignment:
            sticky = self._valid_sticky(shippers, orders)
            free = [s for s in shippers if len(s.bag) < s.K_max]
            idle_without_assignment = any(
                not s.bag and s.id not in sticky and len(s.bag) < s.K_max
                for s in shippers
            )
            force_replan = (
                (not sticky and bool(unpicked))
                or idle_without_assignment
                or len(obs.get("new_order_ids", [])) >= max(3, self.C // 3)
            )
            due_replan = t - self._last_plan_t >= self._large_replan_interval()
            if not force_replan and not due_replan:
                self._assignments = sticky
                return dict(sticky)
            if not unpicked or not free:
                self._assignments = sticky
                self._last_plan_t = t
                return dict(sticky)

            _, by_shipper, score_map = self._large_score_matrix(free, unpicked, orders, t)
            best_assign = self._large_greedy_assign(free, by_shipper, sticky)
            best_q = self._large_evaluate(best_assign, score_map, shippers, orders, t)

            # Keep ACO exploration on the reduced score matrix only.
            for _ in range(max(1, self._num_iter)):
                for _ in range(max(2, min(self._num_ants, 8))):
                    ant = self._large_ant_construct(free, by_shipper, score_map, sticky)
                    q = self._large_evaluate(ant, score_map, shippers, orders, t)
                    if q > best_q:
                        best_q = q
                        best_assign = dict(ant)
                self._evaporate()
                if best_q > 0:
                    self._deposit(best_assign, best_q / 100.0)
            self._assignments = dict(best_assign)
            self._last_plan_t = t
            return dict(best_assign)

        greedy = self._greedy_assign(shippers, orders, t)
        best_q = self._evaluate(greedy, shippers, orders, t)
        best_assign = dict(greedy)

        self._step_counter += 1
        if self._step_counter >= self._aco_interval:
            self._step_counter = 0
            free = [s for s in shippers if len(s.bag) < s.K_max]
            unpicked = [o for o in orders.values() if not o.picked and not o.delivered]
            if unpicked and free:
                top_k = min(self._candidate_k, len(unpicked))
                # Use global reward-based scoring for candidate diversity across large maps
                # Distance-weighted scoring would bias toward nearby orders, starving distant queues
                scored = sorted(unpicked, key=lambda o:
                    -{1: 1.0, 2: 2.5, 3: 5.0}[o.p] * delivery_reward(o, t + 5, self.T))
                candidates = scored[:top_k]
                for _ in range(self._num_iter):
                    for _ in range(self._num_ants):
                        ant = self._ant_construct(free, candidates, t, orders)
                        q = self._evaluate(ant, shippers, orders, t)
                        if q > best_q:
                            best_q = q
                            best_assign = dict(ant)
                    self._evaporate()
                    if best_q > 0:
                        self._deposit(best_assign, best_q / 100.0)
        # Secondary greedy: cover shippers missed by main assignment
        assigned_orders = set(best_assign.values())
        for s in shippers:
            if s.id in best_assign or len(s.bag) >= s.K_max:
                continue
            best_sc, best_oid = -INF, None
            for o in orders.values():
                if o.picked or o.delivered or o.id in assigned_orders:
                    continue
                sc = self.score_pickup(s, o, t, orders)
                if sc > best_sc:
                    best_sc, best_oid = sc, o.id
            if best_oid is not None:
                best_assign[s.id] = best_oid
                assigned_orders.add(best_oid)

        return best_assign

    def _decide_actions(self, obs: dict, assignments: Dict[int, int]) -> Dict[int, Action]:
        t = obs["t"]
        orders = obs["orders"]
        shippers = obs["shippers"]

        actions: Dict[int, Action] = {}
        desired: Dict[int, Tuple[Move, Position]] = {}

        for s in sorted(shippers, key=lambda x: x.id):
            pos = (s.r, s.c)

            can_deliver = any(
                oid in orders and not orders[oid].delivered
                and (orders[oid].ex, orders[oid].ey) == pos
                for oid in s.bag
            )
            if can_deliver:
                actions[s.id] = ("S", 2)
                desired[s.id] = ("S", pos)
                continue

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
                dest = self._delivery_targets[s.id]
                mv = self._next_move(pos, dest)
                nxt = valid_next_pos(pos, mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                desired[s.id] = (mv, nxt)
                continue

            if s.id in assignments and len(s.bag) < s.K_max:
                oid = assignments[s.id]
                if oid in orders and not orders[oid].picked:
                    goal = (orders[oid].sx, orders[oid].sy)
                    mv = self._next_move(pos, goal)
                    nxt = valid_next_pos(pos, mv, self.grid)
                    op = self.choose_cargo_op(s, nxt, orders)
                    actions[s.id] = (mv, op)
                    desired[s.id] = (mv, nxt)
                    continue

            if s.bag and s.id in self._delivery_targets:
                dest = self._delivery_targets[s.id]
                mv = self._next_move(pos, dest)
                nxt = valid_next_pos(pos, mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                desired[s.id] = (mv, nxt)
                continue

            wander = self._wander_target(s, orders)
            mv = self._next_move(pos, wander)
            nxt = valid_next_pos(pos, mv, self.grid)
            actions[s.id] = (mv, 0)
            desired[s.id] = (mv, nxt)

        resolved = self.resolve_moves(desired, shippers)
        for sid, mv in resolved.items():
            if sid in actions:
                s = next(s for s in shippers if s.id == sid)
                nxt = valid_next_pos((s.r, s.c), mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[sid] = (mv, op)
        return actions

    def run(self) -> dict:
        start_time = time.time()
        obs = self.env.reset()
        while not obs.get("done", False):
            assignments = self._plan(obs)
            actions = self._decide_actions(obs, assignments)
            obs, _, done, _ = self.env.step(actions)
            if done:
                break
        return self.env.result(self.method_name, elapsed_sec=time.time() - start_time)
