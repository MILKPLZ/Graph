from __future__ import annotations

from typing import Dict, Optional

from env import Order
from solver_baseline.base import Action, BasicSolver, INF


class GreedyBFS(BasicSolver):
    """Basic Greedy BFS.

    Local decision only: deliver if needed, otherwise go to the best visible
    pickup by priority/deadline/distance. There is no global assignment,
    batching, hotspot learning, or advanced collision handling.
    """

    method_name = "BaselineGreedyBFS"

    def decide_actions(self, obs: dict) -> Dict[int, Action]:
        orders = obs["orders"]
        actions: Dict[int, Action] = {}
        reserved: set[int] = set()

        for shipper in sorted(obs["shippers"], key=lambda s: s.id):
            if self.deliverable_here(shipper, orders):
                actions[shipper.id] = ("S", 2)
                continue
            if self.pickup_here(shipper, orders):
                actions[shipper.id] = ("S", 1)
                continue

            if shipper.bag:
                delivery = self._urgent_or_nearest_delivery(shipper, orders, obs["t"])
                if delivery is not None:
                    actions[shipper.id] = self.move_toward(shipper, (delivery.ex, delivery.ey), orders)
                    continue

            pickup = self._best_local_pickup(shipper, orders, reserved, obs["t"])
            if pickup is not None:
                reserved.add(pickup.id)
                actions[shipper.id] = self.move_toward(shipper, (pickup.sx, pickup.sy), orders)
                continue

            delivery = self.nearest_delivery(shipper, orders)
            if delivery is not None:
                actions[shipper.id] = self.move_toward(shipper, (delivery.ex, delivery.ey), orders)
            else:
                actions[shipper.id] = ("S", 0)

        return actions

    def _best_local_pickup(
        self,
        shipper,
        orders: Dict[int, Order],
        reserved: set[int],
        t: int,
    ) -> Optional[Order]:
        pos = (shipper.r, shipper.c)
        best: Optional[Order] = None
        best_score = -INF
        for order in orders.values():
            if order.picked or order.delivered or order.id in reserved:
                continue
            if not shipper.can_carry(order, orders):
                continue
            d1 = self.bfs_distance(pos, (order.sx, order.sy))
            d2 = self.bfs_distance((order.sx, order.sy), (order.ex, order.ey))
            if d1 >= INF or d2 >= INF:
                continue
            arrival = t + d1 + d2
            score = self.reward_estimate(order, arrival) / max(1, d1 + d2)
            score += self.priority_weight(order) / max(1, order.et - t + 1)
            if score > best_score:
                best = order
                best_score = score
        return best

    def _urgent_or_nearest_delivery(self, shipper, orders: Dict[int, Order], t: int) -> Optional[Order]:
        pos = (shipper.r, shipper.c)
        best: Optional[Order] = None
        best_key = (INF, INF, INF)
        for oid in shipper.bag:
            order = orders.get(oid)
            if order is None or order.delivered:
                continue
            dist = self.bfs_distance(pos, (order.ex, order.ey))
            if dist >= INF:
                continue
            slack = order.et - (t + dist)
            key = (slack, dist, order.id)
            if key < best_key:
                best = order
                best_key = key
        if len(shipper.bag) >= shipper.K_max:
            return best
        return best if best is not None and best_key[0] <= self.N else None

