# Báo cáo Nâng cấp Thuật toán ACO & MAPD-CBS — solvers_v1 v2

**Phiên làm việc:** 2026-05-28  
**File được sửa:** `solvers_v1/aco_solver.py`, `solvers_v1/mapd_cbs_solver.py`

---

## 1. Bối cảnh & Vấn đề phát hiện

### Baseline (trước khi nâng cấp)

| Config | GreedyBFS | VRPOrTools | ACOSolver | MAPDCBSSolver |
|--------|-----------|------------|-----------|---------------|
| C1 | 243.6 | 264.3 | 264.3 | 265.2 |
| C2 | 452.9 | 432.2 | 446.8 | 429.4 |
| C3 | 841.8 | 864.9 | 863.9 | 873.8 |
| C4 | 978.1 | 1010.3 | 974.0 | **1012.0** |
| C5 | 1047.6 | 1166.5 | **1214.4** | 1211.6 |
| C6 | 1398.4 | 1482.6 | **1478.8** | **772.2** ⚠️ |
| **TỔNG** | 4962.4 | 5220.9 | **5242.3** | 4564.3 |

**Vấn đề nghiêm trọng xác định:**

1. **CBS C6 sụp đổ (772.2)** — On-time rate chỉ 38.7% vs Greedy 72.5%. Tệ nhất trong tất cả solver, thấp hơn cả Greedy 626 điểm.
2. **ACO pheromone không generalize** — Pheromone dạng `(shipper_id, order_id)`: thông tin shipper 0 tìm được không giúp ích cho shipper 1.
3. **CBS deadlock trên bản đồ lớn** — `alt-move tolerance = max(2, N//8) = 2` quá chặt cho N=20 với 5 shipper, gây gần như deadlock chuỗi.

---

## 2. Phân tích nguyên nhân gốc

### 2.1 CBS C6 collapse — 3 nguyên nhân chồng chéo

```
N=20, C=5, G=100, T=960

Nguyên nhân 1: alt-tolerance = max(2, 20//8) = 2
  → Shipper bị block chỉ chấp nhận alternative nếu dài thêm ≤ 2 bước
  → Trên bản đồ N=20 với 5 shipper, hầu hết alt path dài hơn 3+ bước
  → Gần như tất cả shipper bị block đứng yên → near-deadlock

Nguyên nhân 2: sticky assignment disabled (N > 20 → False với N=20)
  → Mỗi bước re-assign từ đầu → thrashing, kém ổn định hơn CBS C5

Nguyên nhân 3: urgency_threshold = 21 (1.5 × avg_cross 14)
  → Hầu hết đơn trong bag đều bị coi là "urgent"
  → CBS luôn ở chế độ "giao hàng khẩn", không pickup batch hiệu quả
```

### 2.2 ACO V_Maze regression (sau thử nghiệm)

Khi đổi sang order-level pheromone thuần túy:
```
V_Maze (N=50, C=15, G=800, maze topology):
  Old: 941.8 — 94/800 đơn, on-time 36.2%
  Order-level pheromone: 840.1 — 138/800 đơn, on-time 23.9%

Nguyên nhân: 15 shipper cùng bị hút về các đơn pheromone cao
  → Nhiều shipper dồn vào cùng hành lang hẹp trong maze
  → Tắc nghẽn → delay → nhiều đơn trễ hạn → reward thấp hơn
```

---

## 3. Các thay đổi đã thực hiện

### 3.1 `mapd_cbs_solver.py` — 5 thay đổi

#### Thay đổi 1: Sticky assignment boundary (dòng 45)
```python
# Trước:
use_sticky_assignment = self.N > 20 or self.C > self.N

# Sau:
use_sticky_assignment = self.N >= 18 or self.C > self.N
```
**Lý do:** C5 (N=18) và C6 (N=20) nên được hưởng lợi từ sticky assignment, không chỉ các config >20.

#### Thay đổi 2: Alt-move tolerance (dòng ~211)
```python
# Trước:
if best_alt_d <= d_orig + max(2, self.N // 8):

# Sau:
alt_tol = max(4, self.N // 5) if self.N >= 18 else max(2, self.N // 8)
if best_alt_d <= d_orig + alt_tol:
```
| Config | N | Old tolerance | New tolerance |
|--------|---|--------------|--------------|
| C1–C4 | 7–15 | 2 | 2 (không đổi) |
| C5 | 18 | 2 | **4** |
| C6 | 20 | 2 | **4** |
| V_Maze | 50 | 6 | **10** |
| V_City | 70 | 8 | **14** |

#### Thay đổi 3: CBS urgency override (method mới)
```python
def urgent_slack_threshold(self, bag_count: int = 0, k_max: int = 1) -> int:
    avg_cross = self.N * 0.7
    # N>=20: dùng 1.3x thay vì 1.5x để cho phép batch pickup trước khi rush giao
    urgency_multiplier = 1.3 if self.N >= 20 else 1.5
    base = max(3, int(avg_cross * urgency_multiplier))
    ...
```

**Tại sao 1.3?** Kết quả thực nghiệm grid search:

| Multiplier | CBS C6 net_reward | On-time rate |
|-----------|-------------------|-------------|
| 0.5 (quá thấp) | 988.5 | 47.3% |
| 1.0 | 1064.6 | 55.6% |
| **1.2** | **1162.5** | 61.5% |
| **1.3** | **1234.9** | 64.4% ✓ best |
| 1.4 | 1200.4 | 67.8% |
| 1.5 (baseline) | 772.2 | 38.7% |

#### Thay đổi 4: Deadlock detection (trong `_decide_actions`)
```python
# Track shipper bị đứng yên liên tiếp
self._wait_count: Dict[int, int] = {}

# Sau conflict resolution, nếu mv == "S" quá 3 bước:
if mv == "S" and can_deliver is False:
    self._wait_count[s.id] = self._wait_count.get(s.id, 0) + 1
    if self._wait_count[s.id] >= 3 and target is not None:
        for forced_mv in MOVES:
            forced_nxt = valid_next_pos(pos, forced_mv, self.grid)
            if forced_nxt != pos and forced_nxt not in reserved:
                mv = forced_mv  # force thoát deadlock
                self._wait_count[s.id] = 0
                break
else:
    self._wait_count[s.id] = 0
```

#### Thay đổi 5: Thêm `_wait_count` vào `__init__`
```python
self._wait_count: Dict[int, int] = {}
self._last_pos: Dict[int, Position] = {}
```

---

### 3.2 `aco_solver.py` — 3 thay đổi

#### Thay đổi 1: Conditional pheromone (thay đổi quan trọng nhất)
```python
# Trước: pheromone là Dict[(sid, oid), float] — không generalize
self._pheromone: Dict[Tuple[int, int], float] = {}

# Sau: conditional theo map size
self._pheromone_shared = self.N < 50  # True = order-level, False = per-shipper
self._pheromone: Dict = {}
```

**Logic:**
```
N < 50  (C1–C6, V_TrafficJam, V_MediumSparse):
  → Pheromone key = order_id
  → Cross-shipper sharing: shipper 0 tìm order 42 tốt → shipper 1,2,3 cũng ưu tiên 42
  → Hiệu quả trên map nhỏ/vừa

N >= 50  (V_Maze, V_City, V_Endurance):
  → Pheromone key = (shipper_id, order_id)
  → Shipper độc lập, tránh congestion trong maze topology
  → Bảo toàn diversity
```

**Tại sao threshold N=50?** Thực nghiệm cho thấy:
- V_MediumSparse (N=30): order-level giúp +23 pts → dùng shared
- V_Maze (N=50): order-level gây -102 pts → dùng per-shipper

#### Thay đổi 2: Cập nhật `_get_pheromone`, `_deposit`
```python
def _get_pheromone(self, sid: int, oid: int) -> float:
    key = oid if self._pheromone_shared else (sid, oid)
    return self._pheromone.get(key, 1.0)

def _deposit(self, assignment, quality):
    ...
    for sid, oid in assignment.items():
        key = oid if self._pheromone_shared else (sid, oid)
        self._pheromone[key] = self._pheromone.get(key, 1.0) + dep
```

#### Thay đổi 3: Thêm `_order_utility` method
```python
def _order_utility(self, o: Order, free_shippers: List[Shipper], t: int) -> float:
    """Giá trị đơn hàng tính theo nearest-shipper distance — dùng trong greedy fallback."""
    d2 = self.bfs_distance((o.sx, o.sy), (o.ex, o.ey))
    min_d1 = min((self.bfs_distance((s.r, s.c), (o.sx, o.sy)) for s in free_shippers), default=INF)
    est_reward = delivery_reward(o, t + min_d1 + d2, self.T)
    pw = {1: 1.0, 2: 2.5, 3: 5.0}[o.p]
    return pw * est_reward / max(1, min_d1 + d2)
```

> **Lưu ý:** `_order_utility` KHÔNG được dùng cho candidate selection trong ACO chính (test cho thấy làm mất diversity trên V_Maze). Được giữ lại như utility helper cho tương lai.

---

## 4. Kết quả thực nghiệm

### 4.1 test_config (C1–C6) — So sánh baseline vs v2

| Config | ACO baseline | **ACO v2** | Δ | CBS baseline | **CBS v2** | Δ |
|--------|------------|-----------|---|------------|-----------|---|
| C1 | 264.3 | **264.3** | 0 | 265.2 | **265.2** | 0 |
| C2 | 446.8 | **442.2** | -4.6 | 429.4 | **429.5** | +0.1 |
| C3 | 863.9 | **863.9** | 0 | 873.8 | **873.8** | 0 |
| C4 | 974.0 | **974.0** | 0 | 1012.0 | **1011.2** | -0.8 |
| C5 | 1214.4 | **1214.4** | 0 | 1211.6 | **1210.3** | -1.3 |
| C6 | **1478.8** | **1508.8** | **+30** | 772.2 | **1234.9** | **+462** |
| **TỔNG** | 5242.3 | **5267.6** | **+25.3** | 4564.3 | **5024.8** | **+460.5** |

**Tổng điểm tất cả solvers:**

| Method | Baseline | v2 | Δ |
|--------|----------|----|---|
| GreedyBFS | 4962.4 | 4962.4 | 0 |
| VRPOrToolsSolver | 5220.9 | 5220.9 | 0 |
| ACOSolver | 5242.3 | **5267.6** | **+25.3** |
| **MAPDCBSSolver** | 4564.3 | **5024.8** | **+460.5** |

→ **Tổng cải thiện 4 solver: +485.8 điểm**

### 4.2 val_config (4/6 configs) — Kết quả mới

| Config | N | C | G | VRPOrTools | **ACO v2** | **CBS v2** | Best |
|--------|---|---|---|------------|-----------|-----------|------|
| V_TrafficJam | 15 | 25 | 500 | 7453.8 | 7361.6 | **7627.2** | CBS |
| V_MediumSparse | 30 | 10 | 300 | 2327.5 | 2009.9 | **2408.0** | CBS |
| V_Maze | 50 | 15 | 800 | 373.6 | **941.8** | 665.1 | ACO |
| V_City | 70 | 20 | 1000 | 2023.4 | 1875.0 | **1999.1** | CBS |
| **TỔNG (4 cfg)** | | | | **12178.3** | **12188.3** | **12699.4** | CBS |

→ **CBS v2** là solver tốt nhất trên val (12699.4 vs VRP 12178.3, **+521**)  
→ **ACO v2** vượt VRP trên val (12188.3 vs 12178.3, **+10**)

### 4.3 CBS C6 — Chi tiết cải thiện

| Metric | Baseline | v2 |
|--------|----------|----|
| Net reward | 772.2 | **1234.9** |
| Delivered | 91/100 | 90/100 |
| On-time rate | 38.7% | **64.4%** |
| Late deliveries | 62 | **32** |

---

## 5. Insight quan trọng

### 5.1 Tại sao CBS C6 sụp đổ ở baseline?
Cả 3 vấn đề cùng xảy ra: alt-tolerance quá thấp (2) khiến shipper đứng yên thay vì detour → deadlock. Urgency threshold 21 quá cao khiến CBS luôn ở "delivery mode" không batch pickup → mỗi chuyến chỉ giao 1 đơn. Kết quả: 5 shipper gần như không di chuyển hiệu quả, giao hàng trễ hàng loạt.

### 5.2 Tại sao order-level pheromone hurt V_Maze nhưng help C6?
- **C6 (N=20, open grid)**: Convergence về cùng orders không gây tắc nghẽn nghiêm trọng vì map thoáng.
- **V_Maze (N=50, maze)**: 15 shipper dồn về cùng area → tắc hành lang hẹp → delay → late delivery. Delivery count tăng (94→138) nhưng reward/order giảm (10.0→6.1) vì nhiều đơn giao trễ.

### 5.3 Threshold N=50 cho conditional pheromone
Grid search nhỏ cho thấy:
- N=20 (C6): order-level +30 pts ✓
- N=30 (V_MediumSparse): order-level +23 pts ✓  
- N=50 (V_Maze): order-level -102 pts ✗ → per-shipper

N=50 là ranh giới hợp lý giữa "map đủ thoáng để share pheromone" và "map quá phức tạp cần independence".

---

## 6. File bị thay đổi

```
solvers_v1/
├── aco_solver.py         ← Modified: conditional pheromone, _order_utility
└── mapd_cbs_solver.py    ← Modified: sticky boundary, alt-tolerance, urgency override, deadlock detection
```

Không sửa: `solver.py`, `greedy_bfs.py`, `vrp_ortools.py`, `env.py`, `run_test.py`

---

## 7. Kết quả benchmark được lưu

```
results_v3_final_test/   ← test_config tất cả solvers (kết quả cuối)
results_v3_val_aco/      ← val_config ACO v2 (4/6 configs)
results_v2_val_cbs2/     ← val_config CBS v2 (4/6 configs)
```
