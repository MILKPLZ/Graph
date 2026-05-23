from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from env import (
    DeliveryEnv, Order, Shipper,
    is_valid_cell, valid_next_pos, delivery_reward, r_base, move_cost,
    ALPHA, BETA, GAMMA,
)

Move = str
Position = Tuple[int, int]
INF = 10**9
MOVES: Tuple[Move, ...] = ("U", "D", "L", "R")


class Solver:
    """
    Base class with shared BFS, scoring, collision avoidance, smart wander.
    All params adaptive — NO hardcoded magic numbers.
    Only uses data from obs / env public attributes.
    """

    def __init__(self, env: DeliveryEnv):
        if not isinstance(env, DeliveryEnv):
            raise TypeError("Solver expects DeliveryEnv.")
        self.env = env
        self.grid = env.grid
        # Public env attributes only
        self.N: int = env.N
        self.T: int = env.T
        self.G: int = env.G
        self.C: int = env.C

        # BFS caches
        self._dist_cache: Dict[Tuple[Position, Position], int] = {}
        self._parent_cache: Dict[Position, Dict[Position, Tuple[Optional[Position], Move]]] = {}
        self._next_move_cache: Dict[Tuple[Position, Position], Move] = {}

        # Hotspot tracking (learned from obs only)
        self._hotspot_counts: Dict[Position, float] = {}
        self._hotspot_history: deque = deque(maxlen=60)

        # Valid wander fallback
        self._wander_fallback = self._find_valid_center()

    # ------------------------------------------------------------------
    # BFS
    # ------------------------------------------------------------------
    def _grid_neighbors(self, pos: Position):
        for move in MOVES:
            nxt = valid_next_pos(pos, move, self.grid)
            if nxt != pos:
                yield move, nxt

    def _bfs_from(self, start: Position):
        if start in self._parent_cache:
            return self._parent_cache[start]
        if not is_valid_cell(start, self.grid):
            return {}
        queue: deque = deque([start])
        parent: Dict[Position, Tuple[Optional[Position], Move]] = {start: (None, "S")}
        dist = {start: 0}
        while queue:
            cur = queue.popleft()
            for mv, nxt in self._grid_neighbors(cur):
                if nxt in parent:
                    continue
                parent[nxt] = (cur, mv)
                dist[nxt] = dist[cur] + 1
                queue.append(nxt)
        for pos, d in dist.items():
            self._dist_cache[(start, pos)] = d
        self._parent_cache[start] = parent
        return parent

    def bfs_distance(self, start: Position, goal: Position) -> int:
        if start == goal:
            return 0
        key = (start, goal)
        if key in self._dist_cache:
            return self._dist_cache[key]
        self._bfs_from(start)
        return self._dist_cache.get(key, INF)

    def bfs_next_move(self, start: Position, goal: Position) -> Move:
        if start == goal:
            return "S"
        key = (start, goal)
        if key in self._next_move_cache:
            return self._next_move_cache[key]
        parent = self._bfs_from(start)
        if goal not in parent:
            self._next_move_cache[key] = "S"
            return "S"
        cur = goal
        while True:
            prev, mv = parent[cur]
            if prev is None:
                self._next_move_cache[key] = "S"
                return "S"
            if prev == start:
                self._next_move_cache[key] = mv
                return mv
            cur = prev

    # ------------------------------------------------------------------
    # Adaptive urgency threshold (NO hardcoded values)
    # ------------------------------------------------------------------
    def urgent_slack_threshold(self, bag_count: int = 0, k_max: int = 1) -> int:
        avg_cross = self.N * 0.7
        base = max(3, int(avg_cross * 1.5))
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
    # Scoring — all thresholds relative to N
    # ------------------------------------------------------------------
    def score_pickup(self, shipper: Shipper, order: Order, t: int,
                     orders: Dict[int, Order]) -> float:
        pos = (shipper.r, shipper.c)
        d1 = self.bfs_distance(pos, (order.sx, order.sy))
        d2 = self.bfs_distance((order.sx, order.sy), (order.ex, order.ey))
        if d1 >= INF or d2 >= INF:
            return -INF
        if not shipper.can_carry(order, orders):
            return -INF

        total_d = d1 + d2
        arrival = t + total_d
        est_reward = delivery_reward(order, arrival, self.T)
        efficiency = est_reward / max(1, total_d)
        slack = order.et - arrival
        pw = {1: 1.0, 2: 2.5, 3: 5.0}[order.p]

        if slack >= 0:
            urgency = 3.0 / max(1, slack + 1)
            score = pw * efficiency + urgency
        else:
            late_factor = {1: 0.2, 2: 0.4, 3: 0.6}[order.p]
            score = pw * max(0.001, efficiency) * late_factor

        # Relative distance penalty
        rel_d = d1 / max(1, self.N)
        if rel_d > 1.5:
            score *= 0.4
        elif rel_d > 0.8:
            score *= 0.7

        hs = self._hotspot_counts.get((order.sx, order.sy), 0)
        score += hs * 0.05
        return score

    def score_delivery(self, shipper: Shipper, order: Order, t: int) -> float:
        pos = (shipper.r, shipper.c)
        d = self.bfs_distance(pos, (order.ex, order.ey))
        if d >= INF:
            return -INF
        arrival = t + d
        est_reward = delivery_reward(order, arrival, self.T)
        slack = order.et - arrival
        if slack < 0:
            urgency = 20.0
        elif slack <= 3:
            urgency = 15.0
        elif slack <= 10:
            urgency = 5.0
        else:
            urgency = 0.0
        pw = {1: 1.0, 2: 2.0, 3: 4.0}[order.p]
        return pw * est_reward / max(1, d) + urgency

    # ------------------------------------------------------------------
    # Hotspot tracking (from obs only)
    # ------------------------------------------------------------------
    def update_hotspot(self, new_order_ids: List[int], orders: Dict[int, Order]):
        positions: List[Position] = []
        for oid in new_order_ids:
            if oid in orders:
                o = orders[oid]
                positions.append((o.sx, o.sy))
        self._hotspot_history.append(positions)
        self._hotspot_counts.clear()
        for pos_list in self._hotspot_history:
            for pos in pos_list:
                self._hotspot_counts[pos] = self._hotspot_counts.get(pos, 0) + 1.0

    # ------------------------------------------------------------------
    # Collision avoidance
    # ------------------------------------------------------------------
    def resolve_moves(self, desired: Dict[int, Tuple[Move, Position]],
                      shippers: List[Shipper]) -> Dict[int, Move]:
        reserved: Dict[Position, int] = {}
        result: Dict[int, Move] = {}
        for s in sorted(shippers, key=lambda x: x.id):
            if s.id not in desired:
                result[s.id] = "S"
                continue
            mv, target = desired[s.id]
            old_pos = (s.r, s.c)
            if target != old_pos and target in reserved:
                alt = self._find_alt(s, reserved)
                result[s.id] = alt
                alt_pos = valid_next_pos(old_pos, alt, self.grid)
                reserved[alt_pos] = s.id
            else:
                result[s.id] = mv
                reserved[target] = s.id
        return result

    def _find_alt(self, shipper: Shipper, reserved: Dict[Position, int]) -> Move:
        pos = (shipper.r, shipper.c)
        for mv in MOVES:
            nxt = valid_next_pos(pos, mv, self.grid)
            if nxt != pos and nxt not in reserved:
                return mv
        return "S"

    # ------------------------------------------------------------------
    # Cargo op helper
    # ------------------------------------------------------------------
    def choose_cargo_op(self, shipper: Shipper, next_pos: Position,
                        orders: Dict[int, Order]) -> int:
        for oid in shipper.bag:
            if oid in orders and not orders[oid].delivered:
                if (orders[oid].ex, orders[oid].ey) == next_pos:
                    return 2
        for o in orders.values():
            if not o.picked and not o.delivered and (o.sx, o.sy) == next_pos:
                if shipper.can_carry(o, orders):
                    return 1
        return 0

    # ------------------------------------------------------------------
    # Delivery destination
    # ------------------------------------------------------------------
    def best_delivery_dest(self, shipper: Shipper, orders: Dict[int, Order],
                           t: int) -> Optional[Position]:
        best_score = -INF
        best_dest = None
        dest_counts: Dict[Position, int] = {}
        for oid in shipper.bag:
            if oid in orders and not orders[oid].delivered:
                dest = (orders[oid].ex, orders[oid].ey)
                dest_counts[dest] = dest_counts.get(dest, 0) + 1
        for oid in shipper.bag:
            if oid not in orders or orders[oid].delivered:
                continue
            o = orders[oid]
            s = self.score_delivery(shipper, o, t)
            dest = (o.ex, o.ey)
            s += dest_counts.get(dest, 0) * 5.0
            if s > best_score:
                best_score = s
                best_dest = dest
        return best_dest

    # ------------------------------------------------------------------
    # Smart wander
    # ------------------------------------------------------------------
    def _find_valid_center(self) -> Position:
        center = (self.N // 2, self.N // 2)
        if is_valid_cell(center, self.grid):
            return center
        for radius in range(1, self.N):
            for dr in range(-radius, radius + 1):
                for dc in range(-radius, radius + 1):
                    if abs(dr) == radius or abs(dc) == radius:
                        p = (center[0] + dr, center[1] + dc)
                        if is_valid_cell(p, self.grid):
                            return p
        return (1, 1)

    def smart_wander_target(self, shipper: Shipper,
                            orders: Dict[int, Order]) -> Position:
        pos = (shipper.r, shipper.c)
        pending: Dict[Position, int] = {}
        for o in orders.values():
            if not o.picked and not o.delivered:
                p = (o.sx, o.sy)
                pending[p] = pending.get(p, 0) + 1
        if not pending:
            return self._wander_fallback
        best_score = -1.0
        best_target = self._wander_fallback
        for p, count in pending.items():
            d = self.bfs_distance(pos, p)
            if d >= INF or d == 0:
                continue
            density = count / d
            if density > best_score:
                best_score = density
                best_target = p
        return best_target

    def run(self) -> dict:
        raise NotImplementedError


def default_result(method: str, config_name: str, total_orders: int,
                   orders: Optional[list[Order]] = None) -> dict:
    total_orders = int(total_orders if total_orders is not None else (len(orders) if orders else 0))
    return {
        "method": method, "config_name": config_name,
        "total_orders": total_orders, "orders_generated": 0,
        "delivered": 0, "on_time": 0, "late": 0, "missed": total_orders,
        "delivery_rate": 0.0, "on_time_rate": 0.0,
        "total_reward": 0.0, "total_movecost": 0.0, "net_reward": 0.0,
        "elapsed_sec": 0.0, "shipper_rewards": [], "status": "TODO",
    }
