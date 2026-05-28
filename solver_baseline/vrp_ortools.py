from __future__ import annotations

from typing import Dict, List, Tuple

from env import Order
from solver_baseline.base import Action, BasicSolver, INF


class VRPOrToolsSolver(BasicSolver):
    """Basic VRP-style rolling assignment.

    This baseline keeps the VRP idea of assigning visible jobs to vehicles in
    a batch, but replaces a full OR-Tools route model with one greedy matching
    pass. Each shipper receives at most one current pickup target.
    """

    method_name = "BaselineVRPOrToolsSolver"

    def __init__(self, env):
        super().__init__(env)
        self.assignments: Dict[int, int] = {}

    def decide_actions(self, obs: dict) -> Dict[int, Action]:
        orders = obs["orders"]
        self.assignments = self._batch_assign(obs)
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

    def _batch_assign(self, obs: dict) -> Dict[int, int]:
        t = obs["t"]
        orders = obs["orders"]
        candidates: List[Tuple[float, int, int]] = []

        for shipper in obs["shippers"]:
            if len(shipper.bag) >= shipper.K_max:
                continue
            pos = (shipper.r, shipper.c)
            for order in orders.values():
                if order.picked or order.delivered:
                    continue
                if not shipper.can_carry(order, orders):
                    continue
                d1 = self.bfs_distance(pos, (order.sx, order.sy))
                d2 = self.bfs_distance((order.sx, order.sy), (order.ex, order.ey))
                if d1 >= INF or d2 >= INF:
                    continue
                route_len = d1 + d2
                score = self.reward_estimate(order, t + route_len) / max(1, route_len)
                candidates.append((score, shipper.id, order.id))

        candidates.sort(reverse=True)
        used_shippers: set[int] = set()
        used_orders: set[int] = set()
        assignments: Dict[int, int] = {}
        for _, sid, oid in candidates:
            if sid in used_shippers or oid in used_orders:
                continue
            assignments[sid] = oid
            used_shippers.add(sid)
            used_orders.add(oid)
        return assignments

