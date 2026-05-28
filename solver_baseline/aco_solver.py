from __future__ import annotations

import random
from typing import Dict, List, Tuple

from env import Order
from solver_baseline.base import Action, BasicSolver, INF


class ACOSolver(BasicSolver):
    """Basic Ant Colony Optimization assignment.

    The baseline uses a tiny ant population to choose shipper-order pairings.
    Pheromone is maintained on `(shipper_id, order_id)`. Movement after the
    assignment is still one-step BFS.
    """

    method_name = "BaselineACOSolver"

    def __init__(self, env):
        super().__init__(env)
        self.rng = random.Random(42)
        self.pheromone: Dict[Tuple[int, int], float] = {}
        self.assignments: Dict[int, int] = {}
        self.num_ants = 6
        self.evaporation = 0.3

    def decide_actions(self, obs: dict) -> Dict[int, Action]:
        orders = obs["orders"]
        self.assignments = self._plan(obs)
        actions: Dict[int, Action] = {}

        for shipper in sorted(obs["shippers"], key=lambda s: s.id):
            if self.deliverable_here(shipper, orders):
                actions[shipper.id] = ("S", 2)
                continue
            if self.pickup_here(shipper, orders):
                actions[shipper.id] = ("S", 1)
                continue

            if len(shipper.bag) >= shipper.K_max:
                delivery = self.nearest_delivery(shipper, orders)
                if delivery is not None:
                    actions[shipper.id] = self.move_toward(shipper, (delivery.ex, delivery.ey), orders)
                    continue

            oid = self.assignments.get(shipper.id)
            if oid in orders and not orders[oid].picked:
                order = orders[oid]
                actions[shipper.id] = self.move_toward(shipper, (order.sx, order.sy), orders)
                continue

            delivery = self.nearest_delivery(shipper, orders)
            if delivery is not None:
                actions[shipper.id] = self.move_toward(shipper, (delivery.ex, delivery.ey), orders)
            else:
                actions[shipper.id] = ("S", 0)

        return actions

    def _plan(self, obs: dict) -> Dict[int, int]:
        shippers = [s for s in obs["shippers"] if len(s.bag) < s.K_max]
        orders = obs["orders"]
        candidates = [o for o in orders.values() if not o.picked and not o.delivered]
        if not shippers or not candidates:
            return {}

        best_assignment: Dict[int, int] = {}
        best_score = -INF
        for _ in range(self.num_ants):
            assignment = self._construct_ant(shippers, candidates, orders, obs["t"])
            score = self._evaluate(assignment, obs)
            if score > best_score:
                best_assignment = assignment
                best_score = score

        self._evaporate()
        if best_score > 0:
            deposit = best_score / max(1, len(best_assignment))
            for sid, oid in best_assignment.items():
                self.pheromone[(sid, oid)] = self.pheromone.get((sid, oid), 1.0) + deposit / 100.0
        return best_assignment

    def _construct_ant(self, shippers, candidates: List[Order], orders, t: int) -> Dict[int, int]:
        assignment: Dict[int, int] = {}
        used_orders: set[int] = set()
        shuffled = list(shippers)
        self.rng.shuffle(shuffled)

        for shipper in shuffled:
            weighted: List[Tuple[Order, float]] = []
            pos = (shipper.r, shipper.c)
            for order in candidates:
                if order.id in used_orders or not shipper.can_carry(order, orders):
                    continue
                d1 = self.bfs_distance(pos, (order.sx, order.sy))
                d2 = self.bfs_distance((order.sx, order.sy), (order.ex, order.ey))
                if d1 >= INF or d2 >= INF:
                    continue
                heuristic = self.reward_estimate(order, t + d1 + d2) / max(1, d1 + d2)
                tau = self.pheromone.get((shipper.id, order.id), 1.0)
                weighted.append((order, max(1e-6, tau * heuristic)))

            chosen = self._weighted_choice(weighted)
            if chosen is not None:
                assignment[shipper.id] = chosen.id
                used_orders.add(chosen.id)
        return assignment

    def _weighted_choice(self, weighted: List[Tuple[Order, float]]):
        total = sum(weight for _, weight in weighted)
        if total <= 0:
            return None
        pick = self.rng.random() * total
        seen = 0.0
        for order, weight in weighted:
            seen += weight
            if seen >= pick:
                return order
        return weighted[-1][0]

    def _evaluate(self, assignment: Dict[int, int], obs: dict) -> float:
        orders = obs["orders"]
        shippers = {s.id: s for s in obs["shippers"]}
        score = 0.0
        for sid, oid in assignment.items():
            shipper = shippers.get(sid)
            order = orders.get(oid)
            if shipper is None or order is None:
                continue
            d1 = self.bfs_distance((shipper.r, shipper.c), (order.sx, order.sy))
            d2 = self.bfs_distance((order.sx, order.sy), (order.ex, order.ey))
            if d1 < INF and d2 < INF:
                score += self.reward_estimate(order, obs["t"] + d1 + d2) / max(1, d1 + d2)
        return score

    def _evaporate(self) -> None:
        for key in list(self.pheromone.keys()):
            self.pheromone[key] *= 1.0 - self.evaporation
            if self.pheromone[key] < 0.05:
                del self.pheromone[key]

