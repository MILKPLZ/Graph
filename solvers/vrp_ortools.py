from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from env import DeliveryEnv, Order, Shipper, valid_next_pos
from solvers_v1.solver import Solver, INF, MOVES, Position, Move

Action = Tuple[Move, object]


class VRPOrToolsSolver(Solver):
    """
    VRP V5 — Rolling-horizon global batch matching.
    - Re-plan every step
    - Adaptive urgency, detour bonus, smart wander
    - No hardcoded thresholds
    """

    method_name = "VRPOrToolsSolver"

    def __init__(self, env: DeliveryEnv):
        super().__init__(env)
        self._assignments: Dict[int, int] = {}
        self._delivery_targets: Dict[int, Position] = {}

    def _batch_assign(self, obs: dict):
        t = obs["t"]
        orders = obs["orders"]
        shippers = obs["shippers"]
        self.update_hotspot(obs.get("new_order_ids", []), orders)

        # Update delivery targets
        for s in shippers:
            if s.bag:
                dest = self.best_delivery_dest(s, orders, t)
                if dest:
                    self._delivery_targets[s.id] = dest
                else:
                    self._delivery_targets.pop(s.id, None)
            else:
                self._delivery_targets.pop(s.id, None)

        # Global score matrix
        unpicked = [o for o in orders.values() if not o.picked and not o.delivered]
        scores: List[Tuple[float, int, int]] = []
        use_generalized_detour = self.N > 20 or self.C > self.N
        detour_thresh = max(3, self.N // 2) if use_generalized_detour else max(3, self.N // 4)

        for s in shippers:
            if len(s.bag) >= s.K_max:
                continue
            for o in unpicked:
                sc = self.score_pickup(s, o, t, orders)
                if sc > -INF:
                    bonus = 0.0
                    if s.id in self._delivery_targets:
                        dd = self._delivery_targets[s.id]
                        d_detour = self.bfs_distance(dd, (o.sx, o.sy))
                        if d_detour < detour_thresh:
                            bonus = max(0.5, sc * 0.15) if use_generalized_detour else 2.0
                    scores.append((sc + bonus, s.id, o.id))

        scores.sort(key=lambda x: -x[0])
        assigned_s: set = set()
        assigned_o: set = set()
        new_assign: Dict[int, int] = {}
        for sc, sid, oid in scores:
            if sid in assigned_s or oid in assigned_o:
                continue
            new_assign[sid] = oid
            assigned_s.add(sid)
            assigned_o.add(oid)
        self._assignments = new_assign

    def _decide_actions(self, obs: dict) -> Dict[int, Action]:
        t = obs["t"]
        orders = obs["orders"]
        shippers = obs["shippers"]

        actions: Dict[int, Action] = {}
        desired: Dict[int, Tuple[Move, Position]] = {}

        for s in sorted(shippers, key=lambda x: x.id):
            pos = (s.r, s.c)

            # Immediate delivery
            can_deliver = any(
                oid in orders and not orders[oid].delivered
                and (orders[oid].ex, orders[oid].ey) == pos
                for oid in s.bag
            )
            if can_deliver:
                actions[s.id] = ("S", 2)
                desired[s.id] = ("S", pos)
                continue

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
                dest = self._delivery_targets[s.id]
                mv = self.bfs_next_move(pos, dest)
                nxt = valid_next_pos(pos, mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                desired[s.id] = (mv, nxt)
                continue

            # Pickup
            if s.id in self._assignments and len(s.bag) < s.K_max:
                oid = self._assignments[s.id]
                if oid in orders and not orders[oid].picked:
                    goal = (orders[oid].sx, orders[oid].sy)
                    mv = self.bfs_next_move(pos, goal)
                    nxt = valid_next_pos(pos, mv, self.grid)
                    op = self.choose_cargo_op(s, nxt, orders)
                    actions[s.id] = (mv, op)
                    desired[s.id] = (mv, nxt)
                    continue

            # Non-urgent delivery
            if s.id in self._delivery_targets and s.bag:
                dest = self._delivery_targets[s.id]
                mv = self.bfs_next_move(pos, dest)
                nxt = valid_next_pos(pos, mv, self.grid)
                op = self.choose_cargo_op(s, nxt, orders)
                actions[s.id] = (mv, op)
                desired[s.id] = (mv, nxt)
                continue

            # Smart wander
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
            self._batch_assign(obs)
            actions = self._decide_actions(obs)
            obs, _, done, _ = self.env.step(actions)
            if done:
                break
        return self.env.result(self.method_name, elapsed_sec=time.time() - start_time)
