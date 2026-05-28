from __future__ import annotations

from typing import Dict, Optional

from env import Order, valid_next_pos
from solver_baseline.base import Action, BasicSolver, INF, MOVES, Position


class MAPDCBSSolver(BasicSolver):
    """Basic MAPD-CBS style solver.

    Layer 1 assigns tasks greedily. Layer 2 reserves next-step cells in priority
    order. This is not full CBS tree search; it is the simplest runnable version
    that exposes the same design direction as the final solver.
    """

    method_name = "BaselineMAPDCBSSolver"

    def __init__(self, env):
        super().__init__(env)
        self.assignments: Dict[int, int] = {}

    def decide_actions(self, obs: dict) -> Dict[int, Action]:
        orders = obs["orders"]
        self.assignments = self._assign_tasks(obs)
        actions: Dict[int, Action] = {}
        reserved: set[Position] = set()

        shippers = sorted(
            obs["shippers"],
            key=lambda s: self._priority_key(s, orders, obs["t"]),
        )

        for shipper in shippers:
            pos = (shipper.r, shipper.c)
            if self.deliverable_here(shipper, orders):
                actions[shipper.id] = ("S", 2)
                reserved.add(pos)
                continue
            if self.pickup_here(shipper, orders):
                actions[shipper.id] = ("S", 1)
                reserved.add(pos)
                continue

            target = self._target_for(shipper, orders, obs["t"])
            if target is None:
                actions[shipper.id] = ("S", 0)
                reserved.add(pos)
                continue

            move = self.bfs_next_move(pos, target)
            next_pos = valid_next_pos(pos, move, self.grid)
            if next_pos in reserved:
                move, next_pos = self._fallback_move(pos, target, reserved)

            op = self.cargo_op_at(shipper, next_pos, orders)
            actions[shipper.id] = (move, op)
            reserved.add(next_pos)

        return actions

    def _assign_tasks(self, obs: dict) -> Dict[int, int]:
        orders = obs["orders"]
        assigned: Dict[int, int] = {}
        used_orders: set[int] = set()
        for shipper in sorted(obs["shippers"], key=lambda s: s.id):
            if len(shipper.bag) >= shipper.K_max:
                continue
            order = self.nearest_order(shipper, orders, used_orders)
            if order is not None:
                assigned[shipper.id] = order.id
                used_orders.add(order.id)
        return assigned

    def _target_for(self, shipper, orders: Dict[int, Order], t: int) -> Optional[Position]:
        delivery = self._urgent_delivery(shipper, orders, t)
        if delivery is not None:
            return delivery.ex, delivery.ey
        oid = self.assignments.get(shipper.id)
        if oid in orders and not orders[oid].picked:
            return orders[oid].sx, orders[oid].sy
        delivery = self.nearest_delivery(shipper, orders)
        if delivery is not None:
            return delivery.ex, delivery.ey
        return None

    def _urgent_delivery(self, shipper, orders: Dict[int, Order], t: int) -> Optional[Order]:
        pos = (shipper.r, shipper.c)
        best: Optional[Order] = None
        best_slack = INF
        for oid in shipper.bag:
            order = orders.get(oid)
            if order is None or order.delivered:
                continue
            dist = self.bfs_distance(pos, (order.ex, order.ey))
            if dist >= INF:
                continue
            slack = order.et - (t + dist)
            if slack < best_slack:
                best = order
                best_slack = slack
        if len(shipper.bag) >= shipper.K_max:
            return best
        return best if best is not None and best_slack <= self.N else None

    def _priority_key(self, shipper, orders: Dict[int, Order], t: int):
        urgent = self._urgent_delivery(shipper, orders, t)
        if urgent is None:
            return (1, shipper.id)
        pos = (shipper.r, shipper.c)
        dist = self.bfs_distance(pos, (urgent.ex, urgent.ey))
        return (0, urgent.et - (t + dist), shipper.id)

    def _fallback_move(self, pos: Position, target: Position, reserved: set[Position]):
        best_move = "S"
        best_pos = pos
        best_dist = self.bfs_distance(pos, target)
        for move in MOVES:
            next_pos = valid_next_pos(pos, move, self.grid)
            if next_pos == pos or next_pos in reserved:
                continue
            dist = self.bfs_distance(next_pos, target)
            if dist < best_dist:
                best_move = move
                best_pos = next_pos
                best_dist = dist
        return best_move, best_pos

