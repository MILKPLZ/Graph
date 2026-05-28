from __future__ import annotations

import time
from collections import deque
from typing import Dict, Iterable, List, Optional, Tuple

from env import DeliveryEnv, Order, Shipper, is_valid_cell, valid_next_pos
# đại diện cho hướng di chuyển
Move = str
# Toạ độ trên lưới, thường là (hàng, cột)
Position = Tuple[int, int]
# Đại diện cho hành động của shipper --> ("R", 0): đi sang phải, không có hành động pickup/delivery
Action = Tuple[Move, int]

INF = 10**9
MOVES: Tuple[Move, ...] = ("U", "D", "L", "R")


class BasicSolver:
    """Small shared toolkit for report baselines.

    This class intentionally keeps only the minimum needed for a working
    online MAPD solver: BFS on the grid, pickup/delivery helpers, and the
    standard env loop.
    """

    method_name = "BasicSolver"

    # Khởi tạo solver với môi trường giao hàng
    def __init__(self, env: DeliveryEnv):
        self.env = env
        self.grid = env.grid
        self.N = env.N
        self.T = env.T
        self._dist_cache: Dict[Tuple[Position, Position], int] = {}
        self._next_move_cache: Dict[Tuple[Position, Position], Move] = {}

    def run(self) -> dict:
        start_time = time.time()
        obs = self.env.reset()
        while not obs.get("done", False):
            actions = self.decide_actions(obs)
            obs, _, done, _ = self.env.step(actions)
            if done:
                break
        return self.env.result(self.method_name, elapsed_sec=time.time() - start_time)

    def decide_actions(self, obs: dict) -> Dict[int, Action]:
        raise NotImplementedError

    def neighbors(self, pos: Position) -> Iterable[Tuple[Move, Position]]:
        for move in MOVES:
            nxt = valid_next_pos(pos, move, self.grid)
            if nxt != pos:
                yield move, nxt

    def bfs_distance(self, start: Position, goal: Position) -> int:
        if start == goal:
            return 0
        key = (start, goal)
        if key in self._dist_cache:
            return self._dist_cache[key]
        rev_key = (goal, start)
        if rev_key in self._dist_cache:
            self._dist_cache[key] = self._dist_cache[rev_key]
            return self._dist_cache[key]
        if not is_valid_cell(start, self.grid) or not is_valid_cell(goal, self.grid):
            return INF

        q: deque[Position] = deque([start])
        dist: Dict[Position, int] = {start: 0}
        while q:
            cur = q.popleft()
            for _, nxt in self.neighbors(cur):
                if nxt in dist:
                    continue
                dist[nxt] = dist[cur] + 1
                if nxt == goal:
                    self._dist_cache[key] = dist[nxt]
                    return dist[nxt]
                q.append(nxt)
        self._dist_cache[key] = INF
        return INF

    def bfs_next_move(self, start: Position, goal: Position) -> Move:
        if start == goal:
            return "S"
        key = (start, goal)
        if key in self._next_move_cache:
            return self._next_move_cache[key]
        if not is_valid_cell(start, self.grid) or not is_valid_cell(goal, self.grid):
            return "S"

        q: deque[Position] = deque([start])
        parent: Dict[Position, Tuple[Optional[Position], Move]] = {start: (None, "S")}
        while q:
            cur = q.popleft()
            for move, nxt in self.neighbors(cur):
                if nxt in parent:
                    continue
                parent[nxt] = (cur, move)
                if nxt == goal:
                    first = self._first_move(parent, start, goal)
                    self._next_move_cache[key] = first
                    return first
                q.append(nxt)
        self._next_move_cache[key] = "S"
        return "S"

    @staticmethod
    def _first_move(
        parent: Dict[Position, Tuple[Optional[Position], Move]],
        start: Position,
        goal: Position,
    ) -> Move:
        cur = goal
        while cur in parent:
            prev, move = parent[cur]
            if prev is None:
                return "S"
            if prev == start:
                return move
            cur = prev
        return "S"

    def deliverable_here(self, shipper: Shipper, orders: Dict[int, Order]) -> bool:
        pos = (shipper.r, shipper.c)
        return any(
            oid in orders
            and not orders[oid].delivered
            and (orders[oid].ex, orders[oid].ey) == pos
            for oid in shipper.bag
        )

    def pickup_here(self, shipper: Shipper, orders: Dict[int, Order]) -> bool:
        pos = (shipper.r, shipper.c)
        return any(
            not order.picked
            and not order.delivered
            and (order.sx, order.sy) == pos
            and shipper.can_carry(order, orders)
            for order in orders.values()
        )

    def cargo_op_at(self, shipper: Shipper, next_pos: Position, orders: Dict[int, Order]) -> int:
        for oid in shipper.bag:
            order = orders.get(oid)
            if order is not None and not order.delivered and (order.ex, order.ey) == next_pos:
                return 2
        for order in orders.values():
            if (
                not order.picked
                and not order.delivered
                and (order.sx, order.sy) == next_pos
                and shipper.can_carry(order, orders)
            ):
                return 1
        return 0

    def move_toward(self, shipper: Shipper, target: Position, orders: Dict[int, Order]) -> Action:
        pos = (shipper.r, shipper.c)
        move = self.bfs_next_move(pos, target)
        next_pos = valid_next_pos(pos, move, self.grid)
        return move, self.cargo_op_at(shipper, next_pos, orders)

    def nearest_order(
        self,
        shipper: Shipper,
        orders: Dict[int, Order],
        reserved: set[int],
    ) -> Optional[Order]:
        pos = (shipper.r, shipper.c)
        best: Optional[Order] = None
        best_key = (INF, INF)
        for order in orders.values():
            if order.picked or order.delivered or order.id in reserved:
                continue
            if not shipper.can_carry(order, orders):
                continue
            dist = self.bfs_distance(pos, (order.sx, order.sy))
            key = (dist, order.id)
            if dist < INF and key < best_key:
                best = order
                best_key = key
        return best

    def nearest_delivery(self, shipper: Shipper, orders: Dict[int, Order]) -> Optional[Order]:
        pos = (shipper.r, shipper.c)
        best: Optional[Order] = None
        best_key = (INF, INF)
        for oid in shipper.bag:
            order = orders.get(oid)
            if order is None or order.delivered:
                continue
            dist = self.bfs_distance(pos, (order.ex, order.ey))
            key = (dist, order.id)
            if dist < INF and key < best_key:
                best = order
                best_key = key
        return best

    def priority_weight(self, order: Order) -> float:
        return {1: 1.0, 2: 2.0, 3: 4.0}.get(order.p, 1.0)

    def reward_estimate(self, order: Order, arrival_t: int) -> float:
        base = 4.0
        if order.w > 30.0:
            base = 30.0
        elif order.w > 10.0:
            base = 20.0
        elif order.w > 3.0:
            base = 15.0
        elif order.w > 0.2:
            base = 10.0
        if arrival_t <= order.et:
            return self.priority_weight(order) * base
        return 0.25 * self.priority_weight(order) * base
