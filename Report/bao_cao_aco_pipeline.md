# Báo cáo thuật toán ACO cho bài toán Multi-Agent Package Delivery

## 1. Bối cảnh thực tế

Trong hệ thống giao hàng nhiều shipper, quyết định phân công đơn hàng không chỉ phụ thuộc vào khoảng cách hiện tại mà còn phụ thuộc vào reward, deadline, priority, capacity và trạng thái các shipper khác. Các thuật toán greedy hoặc VRP matching thường chọn phương án tốt nhất theo score hiện tại, nhưng có thể kẹt ở local optimum: một assignment nhìn tốt ngay lúc này có thể làm mất cơ hội nhận các đơn tốt hơn sau vài bước.

`ACOSolver` đại diện cho hướng metaheuristic: dùng Ant Colony Optimization để tạo nhiều phương án assignment shipper-order, sau đó chọn phương án có chất lượng tốt nhất. Điểm mạnh của ACO là exploration có kiểm soát bằng pheromone: những cặp shipper-order từng tạo assignment tốt sẽ có xác suất được chọn cao hơn, nhưng thuật toán vẫn giữ khả năng thử phương án khác.

Trong bài toán online MAPD, ACO không được dùng như một solver offline tìm route dài cố định. Thay vào đó, nó được dùng như một lớp assignment online: tại mỗi thời điểm, chọn target pickup/delivery cho shipper, rồi di chuyển một bước bằng BFS.

## 2. Phát biểu bài toán

Đầu vào gồm:

- Bản đồ lưới `N x N` có vật cản.
- `C` shipper với `W_max`, `K_max`, vị trí và bag hiện tại.
- Tổng số đơn `G`, nhưng đơn được reveal online.
- Mỗi đơn `o_i = (pickup_i, delivery_i, et_i, w_i, p_i)`.
- Horizon thời gian `T`.

Tại timestep `t`, solver chọn action cho từng shipper:

- Di chuyển một bước `U/D/L/R/S`.
- Nhặt đơn nếu đứng tại pickup.
- Giao đơn nếu đứng tại delivery.

Mục tiêu:

```text
maximize net_reward = delivery_reward - movement_cost
```

Ràng buộc:

- Shipper chỉ đi trên ô hợp lệ.
- Không vượt quá tải trọng và số đơn trong túi.
- Một order chưa picked chỉ nên được gán cho tối đa một shipper.
- Solver chỉ dùng observation hiện tại.

## 3. Mô hình hóa toán học

Mô hình bản đồ thành đồ thị không trọng số:

```text
G_map = (V, E)
```

Khoảng cách ngắn nhất:

```text
d(u, v) = BFS_shortest_path(u, v)
```

Với shipper `k` và order `i`:

```text
route_len(k, i, t) = d(pos_k(t), pickup_i) + d(pickup_i, delivery_i)
arrival(k, i, t) = t + route_len(k, i, t)
```

ACO xây dựng assignment:

```text
A = {(k, i) | shipper k được gán order i}
```

Mỗi ant chọn order cho từng shipper theo xác suất:

```text
P(k chọn i) ∝ τ(k, i)^α * η(k, i)^β
```

Trong đó:

- `τ(k, i)` là pheromone của cặp shipper-order.
- `η(k, i)` là heuristic score, thường dựa trên reward/distance.
- `α, β` điều chỉnh mức tin pheromone và heuristic.

Chất lượng assignment:

```text
Q(A) = tổng reward kỳ vọng của các order được gán
       + reward kỳ vọng của các order đang nằm trong bag
```

Sau mỗi vòng, pheromone bay hơi và assignment tốt được deposit:

```text
τ(k, i) ← (1 - ρ) * τ(k, i)
τ(k, i) ← τ(k, i) + deposit nếu (k, i) thuộc assignment tốt
```

## 4. Baseline: `solver_baseline/aco_solver.py`

Baseline nằm ở:

```text
solver_baseline/aco_solver.py
```

Thiết kế baseline:

- Dùng `num_ants = 6`.
- Pheromone lưu trên cặp `(shipper_id, order_id)`.
- Mỗi ant duyệt các shipper còn capacity, chọn một order theo trọng số:

```text
weight = pheromone * reward_estimate / distance
```

- Chọn assignment có score tốt nhất.
- Bay hơi pheromone với `evaporation = 0.3`.
- Deposit nhẹ cho assignment tốt.
- Sau assignment, shipper đi BFS từng bước đến pickup; nếu túi đầy thì giao nearest delivery.

Điểm mạnh:

- Có exploration, không hoàn toàn deterministic như greedy matching.
- Pheromone giúp ghi nhớ các cặp shipper-order từng tốt.
- Cấu trúc đơn giản, chạy được trong môi trường online.

Điểm yếu:

- Số ant cố định, không scale theo `N`, `G`, `C`.
- Không có greedy fallback mạnh.
- Candidate không được lọc tốt nên sampling dễ nhiễu khi nhiều order.
- Evaluation chưa tính đầy đủ reward của đơn đang trong bag theo cách bản nâng cao làm.
- Chưa có delivery target, urgency, hotspot, collision resolve mạnh.

Kết quả baseline trên `test_config.txt`:

| Config | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ |
|---|---:|---:|---:|---:|---:|
| C1 | 266.56 | 13/15 | 13 | 0 | 2 |
| C2 | 458.51 | 24/25 | 23 | 1 | 1 |
| C3 | 558.93 | 25/40 | 20 | 5 | 15 |
| C4 | 966.38 | 56/60 | 49 | 7 | 4 |
| C5 | 1224.67 | 74/80 | 58 | 16 | 6 |
| C6 | 548.68 | 34/100 | 25 | 9 | 66 |

Tổng baseline:

- Net reward: `4023.73`
- Giao hàng: `226/320`
- Đúng hạn: `188`
- Bỏ lỡ: `94`

Baseline ACO đã khá mạnh ở C4/C5 nhờ exploration, nhưng sụp ở C6 vì số đơn nhiều và assignment stochastic chưa đủ ổn định.

## 5. Cải tiến: từ `solver_baseline` sang `solvers`

Bản cải tiến nằm ở:

```text
solvers/aco_solver.py
solvers/solver.py
```

### 5.1. Greedy baseline trước, ACO sau

Bản cải tiến luôn tạo greedy assignment bằng `score_pickup()` trước. ACO chỉ chạy định kỳ và chỉ thay thế greedy nếu tìm được assignment tốt hơn.

Mục đích:

- Tránh phụ thuộc hoàn toàn vào sampling.
- Đảm bảo mỗi timestep có phương án ổn định.

Tradeoff:

- ACO có ít cơ hội thay đổi quyết định hơn.
- Nhưng đây là tradeoff hợp lý trong môi trường online, nơi một lựa chọn sampling kém có thể làm mất deadline.

### 5.2. Tham số ACO adaptive

Bản cải tiến scale tham số theo kích thước bài:

```text
aco_interval = max(2, N // 5)
num_ants = max(4, min(12, G / (C * 5)))
num_iter = max(2, min(5, 200 / G))
candidate_k = max(15, G // 5)
rho = 0.2
```

Mục đích:

- Bài nhỏ không tốn quá nhiều sampling.
- Bài lớn có đủ ant/candidate để khám phá.

Tradeoff:

- Tham số adaptive vẫn là heuristic.
- Nếu candidate quá lớn, runtime tăng và sampling nhiễu; nếu quá nhỏ, bỏ lỡ order tốt.

### 5.3. Candidate pruning

Thay vì cho ant chọn trong toàn bộ order visible, bản cải tiến chọn top candidate theo priority và reward ước lượng:

```text
candidates = top_k(unpicked orders)
```

Mục đích:

- Giảm nhiễu trong sampling.
- Tập trung ACO vào các order có khả năng tạo reward cao.

Tradeoff:

- Có thể bỏ qua order ít priority nhưng gần và dễ giao.
- Cần cân bằng giữa exploitation và exploration.

### 5.4. Pheromone + heuristic score mạnh hơn

Trong ant construction:

```text
probability ∝ pheromone^1.0 * score_pickup^2.5
```

So với baseline, heuristic không còn là reward_estimate thô mà là `score_pickup()` gồm reward thật, priority, slack, distance penalty và hotspot.

Mục đích:

- Pheromone chỉ định hướng, còn score reward-aware vẫn là tín hiệu chính.
- Giảm khả năng pheromone cũ kéo solver vào quyết định kém khi môi trường thay đổi.

Tradeoff:

- Nếu score heuristic bị overfit, ACO cũng bị kéo theo.
- Pheromone trên `(shipper, order)` có tuổi thọ ngắn vì order online chỉ tồn tại trong episode.

### 5.5. Evaluation tính cả đơn đang trong bag

Bản cải tiến `_evaluate()` không chỉ tính assignment pickup mới, mà còn cộng reward kỳ vọng của các order đang nằm trong bag.

Mục đích:

- Tránh assignment pickup mới làm shipper bỏ quên đơn đang mang.
- Cân bằng pickup và delivery.

Tradeoff:

- Evaluation phức tạp hơn.
- Vẫn chỉ là ước lượng myopic, chưa mô phỏng toàn route nhiều điểm.

### 5.6. Delivery target, urgency, smart wander, collision resolve

ACO cải tiến dùng các helper chung của `Solver`:

- `best_delivery_dest()`
- `urgent_slack_threshold()`
- `smart_wander_target()`
- `resolve_moves()`
- BFS cache
- hotspot tracking

Mục đích:

- Sau khi ACO chọn assignment, phần execution vẫn phải xử lý deadline, delivery và xung đột.

Tradeoff:

- Solver không còn là ACO thuần, mà là hybrid greedy-ACO.
- Đổi lại, điểm và độ ổn định tăng rõ.

Kết quả sau cải tiến:

| Config | Baseline | `solvers/ACO` | Chênh lệch | Giao baseline | Giao cải tiến |
|---|---:|---:|---:|---:|---:|
| C1 | 266.56 | 264.34 | -2.22 | 13/15 | 13/15 |
| C2 | 458.51 | 446.83 | -11.68 | 24/25 | 24/25 |
| C3 | 558.93 | 863.92 | +304.99 | 25/40 | 36/40 |
| C4 | 966.38 | 973.98 | +7.60 | 56/60 | 56/60 |
| C5 | 1224.67 | 1214.42 | -10.25 | 74/80 | 75/80 |
| C6 | 548.68 | 1478.79 | +930.10 | 34/100 | 91/100 |

Tổng:

- Baseline: `4023.73`
- `solvers/ACOSolver`: `5242.26`
- Cải thiện: `+1218.54`
- Số đơn giao: `226/320 -> 295/320`
- Đúng hạn: `188 -> 243`
- Bỏ lỡ: `94 -> 25`

Nhận xét:

- Cải thiện chính đến từ C3 và C6.
- C1/C2/C5 giảm nhẹ, cho thấy hybrid heuristic có tradeoff: không phải mọi config nhỏ đều hưởng lợi.
- Tổng điểm vẫn tăng mạnh vì bản cải tiến xử lý tốt bài lớn hơn.

## 6. Final: từ `solvers` sang `solvers_v1`

Bản final nằm ở:

```text
solvers_v1/aco_solver.py
solvers_v1/solver.py
```

Trên `test_config.txt`, final giữ nguyên public score:

```text
5242.26 -> 5242.26
```

Mục tiêu của v1 là anti-overfit và generalization trên map lớn/khó.

### 6.1. Seed theo config cho map lớn/dense

Bản `solvers` dùng seed cố định `42`. Bản `solvers_v1` dùng:

```text
large_or_dense = N > 20 or C > N
seed = 42 + N * 97 + G * 13 + C * 7 nếu large_or_dense
seed = 42 nếu không
```

Mục đích:

- Giữ public test ổn định.
- Tránh cùng một chuỗi random gây hành vi lặp không tốt trên map lớn/dense.

Tradeoff:

- Kết quả ACO phụ thuộc seed.
- Seed theo config là heuristic, không đảm bảo luôn tốt.

### 6.2. Giới hạn candidate trên map lớn/dense

Bản `solvers_v1` đổi:

```text
candidate_k = max(10, min(30, G // 10)) nếu large_or_dense
candidate_k = max(15, G // 5) nếu map nhỏ
```

Mục đích:

- Trên map lớn, quá nhiều candidate làm ant sampling nhiễu và tốn thời gian.
- Giới hạn candidate giúp ACO tập trung vào order tốt.

Tradeoff:

- Candidate nhỏ hơn có thể bỏ qua order tốt nằm ngoài top-k.
- Nhưng thực nghiệm spot-check cho thấy tradeoff này có lợi trên map khó.

### 6.3. Các cải tiến shared từ `solver_v1`

ACO final cũng hưởng lợi từ:

- `_map_radius` thay cho `N` trong distance penalty.
- Hotspot bonus scale theo score trên map lớn/dense.
- Urgency multiplier có điều kiện theo kích thước map.

## 7. Thực nghiệm

### 7.1. Public test

| Phiên bản | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ | Runtime tổng |
|---|---:|---:|---:|---:|---:|---:|
| `solver_baseline/ACOSolver` | 4023.73 | 226/320 | 188 | 38 | 94 | ~2.21s |
| `solvers/ACOSolver` | 5242.26 | 295/320 | 243 | 52 | 25 | ~0.99s |
| `solvers_v1/ACOSolver` | 5242.26 | 295/320 | 243 | 52 | 25 | ~1.29s |

### 7.2. Validation spot-check

Kết quả spot-check cho ACO:

| Config | `solvers` | `solvers_v1` | Chênh lệch | Giao `solvers` | Giao `v1` |
|---|---:|---:|---:|---:|---:|
| V_MediumSparse | 1907.09 | 1986.96 | +79.87 | 186/300 | 196/300 |
| V_Maze | 314.68 | 941.80 | +627.12 | 55/800 | 94/800 |

Spot-check cho thấy final v1 đặc biệt có lợi ở `V_Maze`, nơi candidate pruning và seed theo config giúp ACO không bị sampling quá nhiễu.

## 8. Ablation study

| Mốc | Thành phần chính | Public score | Giao/Tổng | Ý nghĩa |
|---|---|---:|---:|---|
| A0 | ACO baseline: 6 ant, pheromone đơn giản, reward/distance thô | 4023.73 | 226/320 | Có exploration nhưng chưa ổn định trên bài lớn |
| A1 | Greedy fallback, adaptive params, candidate pruning, reward-aware score, delivery/urgency/smart wander | 5242.26 | 295/320 | Tăng mạnh C3/C6 và giảm missed orders |
| A2 | Seed theo config, candidate cap cho map lớn, `_map_radius`, hotspot scale | 5242.26 | 295/320 | Giữ public score, cải thiện spot-check val |

Chi tiết public:

| Config | Baseline | Enhanced | Final v1 | Δ Enhanced-BL | Δ Final-Enhanced |
|---|---:|---:|---:|---:|---:|
| C1 | 266.56 | 264.34 | 264.34 | -2.22 | +0.00 |
| C2 | 458.51 | 446.83 | 446.83 | -11.68 | +0.00 |
| C3 | 558.93 | 863.92 | 863.92 | +304.99 | +0.00 |
| C4 | 966.38 | 973.98 | 973.98 | +7.60 | +0.00 |
| C5 | 1224.67 | 1214.42 | 1214.42 | -10.25 | +0.00 |
| C6 | 548.68 | 1478.79 | 1478.79 | +930.10 | +0.00 |

Phản biện:

- ACO baseline đã mạnh ở một số config nhỏ, nên bản nâng cao không thắng tuyệt đối từng config.
- Cải tiến đáng giá nhất là giảm collapse ở C6: `34/100 -> 91/100`.
- Final v1 nên được đánh giá bằng cả val spot-check vì thay đổi của nó chủ yếu nhắm map lớn/khó.

## 9. Độ phức tạp

Ký hiệu:

- `C`: số shipper.
- `M_t`: số order visible tại timestep `t`.
- `K`: số candidate ACO.
- `A`: số ant.
- `I`: số iteration.
- `V`: số ô trống trên grid.

Baseline mỗi timestep:

```text
O(A * C * M_t * V)
```

Vì mỗi ant có thể duyệt candidate order và gọi BFS distance.

Bản cải tiến:

```text
O(C * M_t * V)                  greedy assignment
+ O(I * A * C * K * V)          ACO định kỳ
```

Do ACO chỉ chạy mỗi `_aco_interval`, chi phí amortized thấp hơn chạy ACO mọi timestep.

Với BFS cache, chi phí thực tế giảm vì nhiều truy vấn distance lặp lại. Bộ nhớ cache:

```text
O(S * V)
```

Trong đó `S` là số start positions từng được BFS.

Tradeoff:

- ACO đắt hơn Greedy/VRP do sampling nhiều assignment.
- Đổi lại, ACO có exploration và đạt điểm public cao nhất trong các solver hiện tại.

## 10. So sánh với các thuật toán khác

Điểm trên `test_config.txt`:

| Thuật toán | Tổng điểm | Vai trò/điểm mạnh |
|---|---:|---|
| ACOSolver | 5242.26 | Exploration trên assignment, điểm public cao nhất |
| VRPOrToolsSolver | 5220.90 | Global batch assignment ổn định, dễ giải thích hơn ACO |
| GreedyBFS | 4962.37 | Nhanh, đơn giản, local policy mạnh |
| MAPDCBSSolver | 4597.89 | Tập trung xử lý conflict multi-agent |

ACO mạnh nhất trên public test nhờ kết hợp greedy baseline và exploration. So với VRP, ACO có khả năng thử assignment không hiển nhiên hơn, nhưng khó giải thích và nhạy với seed/tham số hơn. So với Greedy BFS, ACO phối hợp nhiều shipper tốt hơn. So với MAPD-CBS, ACO chọn task tốt hơn nhưng xử lý xung đột kém chuyên sâu hơn.

## 11. Kết luận

Pipeline ACO:

1. `solver_baseline`: ACO tối giản với pheromone và 6 ant.
2. `solvers`: hybrid greedy-ACO với adaptive params, reward-aware scoring, delivery target, urgency và collision resolve.
3. `solvers_v1`: anti-overfit bằng seed theo config, candidate cap trên map lớn, `_map_radius` và hotspot scale.

Kết quả xác nhận hướng ACO hiệu quả: public score tăng `4023.73 -> 5242.26`, số đơn giao tăng `226/320 -> 295/320`. Điểm mạnh của ACO là exploration có kiểm soát; tradeoff là độ phức tạp, tính ngẫu nhiên và nhu cầu tuning tham số.

