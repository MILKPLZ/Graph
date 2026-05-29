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
                mv = self.bfs_next_move(pos, dest)
                nxt = valid_next_pos(pos, mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                desired[s.id] = (mv, nxt)
                continue

            if s.id in assignments and len(s.bag) < s.K_max:
                oid = assignments[s.id]
                if oid in orders and not orders[oid].picked:
                    goal = (orders[oid].sx, orders[oid].sy)
                    mv = self.bfs_next_move(pos, goal)
                    nxt = valid_next_pos(pos, mv, self.grid)
                    op = self.choose_cargo_op(s, nxt, orders)
                    actions[s.id] = (mv, op)
                    desired[s.id] = (mv, nxt)
                    continue

            if s.bag and s.id in self._delivery_targets:
                dest = self._delivery_targets[s.id]
                mv = self.bfs_next_move(pos, dest)
                nxt = valid_next_pos(pos, mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                desired[s.id] = (mv, nxt)
                continue

            wander = self.smart_wander_target(s, orders)
            mv = self.bfs_next_move(pos, wander)
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
