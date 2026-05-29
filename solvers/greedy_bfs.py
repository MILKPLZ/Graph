from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from env import DeliveryEnv, Order, Shipper, valid_next_pos
from solvers.solver import Solver, INF, MOVES, Position, Move

Action = Tuple[Move, object]


class GreedyBFS(Solver):
    """
    Enhanced Greedy BFS — V5 Anti-Overfit.
    - Adaptive urgency threshold
    - Score-based pickup selection
    - Smart wander toward pending orders
    - Distance-based reservation
    """

    method_name = "GreedyBFS"

    def __init__(self, env: DeliveryEnv):
        super().__init__(env)

    def _select_pickup(self, shipper: Shipper, orders: Dict[int, Order],
                       reserved: set, t: int) -> Optional[Order]:
        best_score = -INF
        best_order = None
        for o in orders.values():
            if o.picked or o.delivered or o.id in reserved:
                continue
            if not shipper.can_carry(o, orders):
                continue
            s = self.score_pickup(shipper, o, t, orders)
            if s > -INF and s > best_score:
                best_score = s
                best_order = o
        # Fallback
        if best_order is None:
            for o in orders.values():
                if o.picked or o.delivered or o.id in reserved:
                    continue
                if not shipper.can_carry(o, orders):
                    continue
                d = self.bfs_distance((shipper.r, shipper.c), (o.sx, o.sy))
                if d < INF:
                    s = 0.01 / max(1, d)
                    if s > best_score:
                        best_score = s
                        best_order = o
        return best_order

    def _decide_actions(self, obs: dict) -> Dict[int, Action]:
        t: int = obs["t"]
        orders: Dict[int, Order] = obs["orders"]
        shippers: List[Shipper] = obs["shippers"]

        self.update_hotspot(obs.get("new_order_ids", []), orders)

        actions: Dict[int, Action] = {}
        reserved: set = set()
        desired: Dict[int, Tuple[Move, Position]] = {}

        for shipper in sorted(shippers, key=lambda s: s.id):
            pos = (shipper.r, shipper.c)

            # Phase 1: Immediate delivery
            can_deliver = any(
                oid in orders and not orders[oid].delivered
                and (orders[oid].ex, orders[oid].ey) == pos
                for oid in shipper.bag
            )
            if can_deliver:
                actions[shipper.id] = ("S", 2)
                desired[shipper.id] = ("S", pos)
                continue

            # Phase 2: Urgency check
            has_urgent = False
            if shipper.bag:
                if len(shipper.bag) >= shipper.K_max:
                    has_urgent = True
                else:
                    threshold = self.urgent_slack_threshold(len(shipper.bag), shipper.K_max)
                    for oid in shipper.bag:
                        if oid in orders and not orders[oid].delivered:
                            o = orders[oid]
                            d = self.bfs_distance(pos, (o.ex, o.ey))
                            if d < INF and o.et - (t + d) < threshold:
                                has_urgent = True
                                break

            if has_urgent:
                dest = self.best_delivery_dest(shipper, orders, t)
                if dest is not None:
                    mv = self.bfs_next_move(pos, dest)
                    nxt = valid_next_pos(pos, mv, self.grid)
                    op = self.choose_cargo_op(shipper, nxt, orders)
                    actions[shipper.id] = (mv, op)
                    desired[shipper.id] = (mv, nxt)
                    continue

            # Phase 3: Pickup
            if len(shipper.bag) < shipper.K_max:
                pickup = self._select_pickup(shipper, orders, reserved, t)
                if pickup is not None:
                    d = self.bfs_distance(pos, (pickup.sx, pickup.sy))
                    if d <= self._map_radius:
                        reserved.add(pickup.id)
                    goal = (pickup.sx, pickup.sy)
                    mv = self.bfs_next_move(pos, goal)
                    nxt = valid_next_pos(pos, mv, self.grid)
                    op = self.choose_cargo_op(shipper, nxt, orders)
                    actions[shipper.id] = (mv, op)
                    desired[shipper.id] = (mv, nxt)
                    continue

            # Phase 4: Non-urgent delivery
            if shipper.bag:
                dest = self.best_delivery_dest(shipper, orders, t)
                if dest is not None:
                    mv = self.bfs_next_move(pos, dest)
                    nxt = valid_next_pos(pos, mv, self.grid)
                    op = self.choose_cargo_op(shipper, nxt, orders)
                    actions[shipper.id] = (mv, op)
                    desired[shipper.id] = (mv, nxt)
                    continue

            # Phase 5: Smart wander
            wander = self.smart_wander_target(shipper, orders)
            mv = self.bfs_next_move(pos, wander)
            nxt = valid_next_pos(pos, mv, self.grid)
            actions[shipper.id] = (mv, 0)
            desired[shipper.id] = (mv, nxt)

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
            actions = self._decide_actions(obs)
            obs, _, done, _ = self.env.step(actions)
            if done:
                break
        return self.env.result(self.method_name, elapsed_sec=time.time() - start_time)
