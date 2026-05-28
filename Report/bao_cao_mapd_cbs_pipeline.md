# Báo cáo thuật toán MAPD-CBS cho bài toán Multi-Agent Package Delivery

## 1. Bối cảnh thực tế

Trong hệ thống nhiều shipper cùng di chuyển trên một bản đồ, chất lượng lời giải không chỉ phụ thuộc vào việc chọn đơn tốt, mà còn phụ thuộc vào khả năng tránh xung đột. Hai shipper có thể muốn đi vào cùng một ô, đi ngược chiều nhau qua một cạnh hẹp, hoặc cùng kẹt ở bottleneck. Đây là nhóm vấn đề Multi-Agent Path Finding/Multi-Agent Pickup and Delivery.

`MAPDCBSSolver` đại diện cho hướng giải quyết tập trung vào conflict avoidance. Thuật toán trong repo là "CBS lite": không triển khai Conflict-Based Search đầy đủ với cây ràng buộc nhiều tầng, nhưng giữ tinh thần hai lớp:

1. Gán task cho shipper.
2. Lập bước di chuyển theo priority và reservation table để tránh conflict.

Điểm mạnh của hướng này là xử lý bài toán multi-agent rõ ràng hơn Greedy/VRP/ACO. Điểm yếu là nếu assignment nền không tốt hoặc reservation quá bảo thủ, solver có thể đứng yên nhiều và giảm reward.

## 2. Phát biểu bài toán

Đầu vào:

- Bản đồ lưới `N x N` có vật cản.
- `C` shipper với vị trí, capacity, bag hiện tại.
- Đơn hàng online `o_i = (pickup_i, delivery_i, et_i, w_i, p_i)`.
- Horizon `T`.

Mỗi timestep, solver chọn action cho từng shipper:

- Move `U/D/L/R/S`.
- Pickup hoặc delivery nếu đứng đúng vị trí.

Mục tiêu:

```text
maximize net_reward = delivery_reward - movement_cost
```

Ràng buộc:

- Không đi vào vật cản hoặc ra ngoài map.
- Không vượt capacity.
- Cần hạn chế vertex conflict: hai shipper cùng muốn vào một ô.
- Cần hạn chế edge-swap conflict: hai shipper đổi chỗ qua cùng một cạnh trong một timestep.

## 3. Mô hình hóa toán học

Mô hình map thành đồ thị:

```text
G_map = (V, E)
```

Mỗi shipper `k` có vị trí `pos_k(t)`. Một kế hoạch một bước là:

```text
a_k(t) ∈ {S, U, D, L, R}
next_k(t) = transition(pos_k(t), a_k(t))
```

Vertex conflict:

```text
next_i(t) = next_j(t), i ≠ j
```

Edge-swap conflict:

```text
pos_i(t) = next_j(t) and pos_j(t) = next_i(t)
```

CBS đầy đủ sẽ thêm constraint và search trên cây conflict. Bản trong repo đơn giản hóa thành reservation một bước:

```text
reserved[next_k(t)] = k
```

Shipper được xử lý theo priority. Nếu ô mục tiêu đã reserved, solver tìm bước thay thế có khoảng cách tới target không tệ quá; nếu không có thì đứng yên.

## 4. Baseline: `solver_baseline/mapd_cbs_solver.py`

Baseline nằm ở:

```text
solver_baseline/mapd_cbs_solver.py
```

Thiết kế baseline:

- Layer 1: assign task bằng nearest feasible order.
- Layer 2: sắp shipper theo urgency đơn giản.
- Mỗi shipper lấy target:
  - delivery khẩn cấp nếu có;
  - pickup được assign;
  - nearest delivery nếu đang có hàng.
- Dùng BFS để lấy bước tiếp theo.
- Nếu next cell đã reserved thì thử fallback move giảm khoảng cách tới target.

Điểm mạnh:

- Có mô hình conflict/reservation ngay từ đầu.
- Dễ mở rộng thành CBS đầy đủ hơn so với Greedy/VRP.
- Tránh được một số vertex conflict đơn giản.

Điểm yếu:

- Assignment nearest order quá yếu.
- Reservation một bước có thể làm shipper đứng yên nhiều.
- Chưa có edge-swap check.
- Chưa có score reward-aware, hotspot, smart wander đủ mạnh.
- Không có CBS tree search thật.

Kết quả baseline:

| Config | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ |
|---|---:|---:|---:|---:|---:|
| C1 | 128.11 | 9/15 | 5 | 4 | 6 |
| C2 | 60.13 | 2/25 | 2 | 0 | 23 |
| C3 | 194.44 | 5/40 | 5 | 0 | 35 |
| C4 | 725.68 | 41/60 | 37 | 4 | 19 |
| C5 | 104.03 | 13/80 | 6 | 7 | 67 |
| C6 | 51.28 | 7/100 | 4 | 3 | 93 |

Tổng baseline:

- Net reward: `1263.66`
- Giao hàng: `77/320`
- Đúng hạn: `59`
- Bỏ lỡ: `243`

Baseline cho thấy chỉ tránh conflict là chưa đủ. Nếu task assignment kém, solver vẫn bỏ lỡ phần lớn đơn.

## 5. Cải tiến: từ `solver_baseline` sang `solvers`

Bản cải tiến nằm ở:

```text
solvers/mapd_cbs_solver.py
solvers/solver.py
```

### 5.1. Layer 1: score-based global task assignment

Baseline gán nearest order. Bản cải tiến dùng `score_pickup()` cho toàn bộ cặp `(shipper, order)`, sau đó greedy matching.

Mục đích:

- Gán đơn dựa trên reward, priority, deadline, distance, capacity.
- Không chỉ chọn đơn gần nhất.

Tradeoff:

- Task assignment phức tạp hơn.
- Vẫn là greedy matching, không phải tối ưu assignment đầy đủ.

### 5.2. Delivery target theo score

Bản cải tiến duy trì `_delivery_targets` cho shipper đang mang hàng, dùng `best_delivery_dest()`.

Mục đích:

- Khi shipper mang nhiều đơn, chọn điểm giao có reward/deadline tốt hơn.
- Tránh nearest delivery đơn giản làm lỡ đơn priority cao.

Tradeoff:

- Có thể đi xa hơn trong ngắn hạn để đổi lấy reward cao hơn.

### 5.3. Priority ordering theo urgency

Trong conflict resolution, shipper được xử lý theo `_shipper_urgency()`:

- Đơn trong bag càng gấp, priority càng cao.
- Order assignment có priority cao cũng tăng urgency.

Mục đích:

- Shipper mang đơn gần deadline được quyền reserve ô trước.
- Giảm khả năng đơn quan trọng bị kẹt sau shipper ít khẩn cấp.

Tradeoff:

- Shipper priority thấp có thể bị nhường đường nhiều và chậm tiến độ.

### 5.4. Reservation table và alternative move

Nếu bước BFS mong muốn đã reserved, solver thử các move khác và chọn move có khoảng cách tới target tốt nhất. Bản `solvers` chấp nhận detour nếu:

```text
best_alt_distance <= original_distance + 2
```

Mục đích:

- Tránh đứng yên khi có đường vòng nhỏ.
- Giảm vertex conflict.

Tradeoff:

- Detour quá hẹp làm solver đứng yên nhiều.
- Detour quá rộng làm shipper đi lệch target.

### 5.5. Edge-swap check

Bản cải tiến kiểm tra nếu một shipper định đi vào ô hiện tại của shipper khác, trong khi shipper kia cũng định đi vào ô của nó.

Mục đích:

- Giảm conflict kiểu đổi chỗ qua cạnh hẹp.

Tradeoff:

- Check vẫn local một bước, không dự đoán bottleneck dài hạn.

### 5.6. Smart wander và helper chung

Khi không có target, solver dùng `smart_wander_target()`. Ngoài ra còn dùng BFS cache, hotspot tracking, urgency threshold và scoring chung từ `Solver`.

Kết quả sau cải tiến:

| Config | Baseline | `solvers/MAPD-CBS` | Chênh lệch | Giao baseline | Giao cải tiến |
|---|---:|---:|---:|---:|---:|
| C1 | 128.11 | 265.24 | +137.13 | 9/15 | 13/15 |
| C2 | 60.13 | 429.45 | +369.32 | 2/25 | 24/25 |
| C3 | 194.44 | 873.76 | +679.32 | 5/40 | 37/40 |
| C4 | 725.68 | 1012.02 | +286.34 | 41/60 | 56/60 |
| C5 | 104.03 | 1245.21 | +1141.18 | 13/80 | 74/80 |
| C6 | 51.28 | 772.21 | +720.94 | 7/100 | 75/100 |

Tổng:

- Baseline: `1263.66`
- `solvers/MAPDCBSSolver`: `4597.89`
- Cải thiện: `+3334.23`
- Giao hàng: `77/320 -> 279/320`
- Đúng hạn: `59 -> 205`
- Bỏ lỡ: `243 -> 41`

Đây là cải thiện rất lớn, chủ yếu vì assignment được thay từ nearest-order sang score-based global assignment.

## 6. Final: từ `solvers` sang `solvers_v1`

Bản final nằm ở:

```text
solvers_v1/mapd_cbs_solver.py
solvers_v1/solver.py
```

Các thay đổi chính:

### 6.1. Sticky assignment có điều kiện

Với map lớn/dense:

```text
use_sticky_assignment = N > 20 or C > N
```

Nếu assignment cũ vẫn hợp lệ, solver giữ lại thay vì reassign liên tục.

Mục đích:

- Giảm dao động target trên map lớn.
- Tránh shipper đổi mục tiêu quá thường xuyên trước khi đến pickup.

Tradeoff:

- Nếu giữ assignment kém quá lâu, solver bỏ lỡ order mới tốt hơn.
- Trên public test nhỏ, điều kiện này không bật.

### 6.2. Urgency scale theo `T`

Bản v1 dùng:

```text
t_scale = max(1, T // 240)
urgency = 100 * t_scale / slack
```

Mục đích:

- Với horizon dài, cùng một slack tuyệt đối có ý nghĩa khác so với horizon ngắn.
- Scale giúp priority ordering phù hợp hơn với bài dài.

Tradeoff:

- Nếu scale quá mạnh, shipper mang hàng có thể chiếm quyền ưu tiên quá lâu.

### 6.3. Detour tolerance theo `N`

Bản `solvers` dùng tolerance cố định `+2`. Bản v1 dùng:

```text
best_alt_distance <= original_distance + max(2, N // 8)
```

Mục đích:

- Trên map lớn, detour hợp lý có thể dài hơn 2 bước.
- Giúp shipper tránh conflict mà không đứng yên quá nhiều.

Tradeoff:

- Detour rộng có thể làm shipper đi lệch target và tăng move cost.

### 6.4. Kết quả final public

Trên `test_config.txt`, v1 giảm nhẹ:

```text
4597.89 -> 4564.26
```

Chênh lệch `-33.63` đến từ C5:

```text
C5: 1245.21 -> 1211.58
```

Phản biện:

- Đây là regression nhỏ so với tổng điểm.
- Các thay đổi v1 nhắm tới map lớn/dense và conflict phức tạp hơn, nhưng chưa chứng minh cải thiện trên public test.
- Với MAPD-CBS, final hiện tại chưa mạnh bằng VRP/ACO; cần thêm benchmark val riêng trước khi khẳng định generalization.

## 7. Thực nghiệm

### 7.1. Public test

| Phiên bản | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ | Runtime tổng |
|---|---:|---:|---:|---:|---:|---:|
| `solver_baseline/MAPDCBSSolver` | 1263.66 | 77/320 | 59 | 18 | 243 | ~1.51s |
| `solvers/MAPDCBSSolver` | 4597.89 | 279/320 | 205 | 74 | 41 | ~0.98s |
| `solvers_v1/MAPDCBSSolver` | 4564.26 | 279/320 | 204 | 75 | 41 | ~1.16s |

### 7.2. Validation hiện có

Kết quả val hiện có cho `MAPDCBSSolver` trong `results_val`:

| Config | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ |
|---|---:|---:|---:|---:|---:|
| V_TrafficJam | 4472.01 | 343/500 | 167 | 176 | 157 |
| V_MediumSparse | 2513.05 | 208/300 | 103 | 105 | 92 |
| V_Maze | 582.35 | 55/800 | 22 | 33 | 745 |
| V_City | 2061.92 | 470/1000 | 68 | 402 | 530 |

Các số liệu này cho thấy MAPD-CBS xử lý được một phần val, nhưng vẫn yếu ở maze/city lớn vì reservation một bước chưa đủ cho bottleneck dài hạn.

## 8. Ablation study

| Mốc | Thành phần chính | Public score | Giao/Tổng | Ý nghĩa |
|---|---|---:|---:|---|
| A0 | Nearest assignment + reservation một bước | 1263.66 | 77/320 | Có conflict awareness nhưng task assignment yếu |
| A1 | Score-based assignment, delivery target, urgency priority, edge-swap, smart wander | 4597.89 | 279/320 | Cải thiện lớn nhờ chọn task tốt hơn và tránh conflict tốt hơn |
| A2 | Sticky assignment, urgency scale, detour tolerance theo N, `_map_radius` | 4564.26 | 279/320 | Regression nhẹ public, hướng tới map lớn nhưng cần tune thêm |

Chi tiết public:

| Config | Baseline | Enhanced | Final v1 | Δ Enhanced-BL | Δ Final-Enhanced |
|---|---:|---:|---:|---:|---:|
| C1 | 128.11 | 265.24 | 265.24 | +137.13 | +0.00 |
| C2 | 60.13 | 429.45 | 429.45 | +369.32 | +0.00 |
| C3 | 194.44 | 873.76 | 873.76 | +679.32 | +0.00 |
| C4 | 725.68 | 1012.02 | 1012.02 | +286.34 | +0.00 |
| C5 | 104.03 | 1245.21 | 1211.58 | +1141.18 | -33.63 |
| C6 | 51.28 | 772.21 | 772.21 | +720.94 | +0.00 |

Phân tích:

- Bước A1 là cải tiến chính.
- Bước A2 chưa đạt mục tiêu trên public test vì giảm nhẹ ở C5.
- CBS-lite hiện tại có điểm mạnh conflict handling, nhưng assignment và multi-step path planning vẫn là điểm cần cải thiện.

## 9. Độ phức tạp

Ký hiệu:

- `C`: số shipper.
- `M_t`: số order visible.
- `V`: số ô trống.
- `E = O(V)` với grid 4-neighbor.

Baseline:

- Assign nearest order cho từng shipper:

```text
O(C * M_t * V)
```

- Reservation một bước:

```text
O(C * 4 * V)
```

Bản cải tiến:

- Score matrix shipper-order:

```text
O(C * M_t * V)
```

- Sort scores:

```text
O((C * M_t) log(C * M_t))
```

- Conflict resolution một bước:

```text
O(C * 4 * V)
```

Với BFS cache, runtime thực tế giảm đáng kể. Bộ nhớ:

```text
O(S * V)
```

Nếu triển khai CBS đầy đủ, độ phức tạp có thể tăng theo số conflict vì phải search trên constraint tree. Bản hiện tại tránh chi phí đó bằng reservation local, đổi lại không giải được bottleneck dài hạn.

## 10. So sánh với các thuật toán khác

Điểm trên `test_config.txt`:

| Thuật toán | Tổng điểm | Vai trò/điểm mạnh |
|---|---:|---|
| ACOSolver | 5242.26 | Exploration trên assignment, điểm public cao nhất |
| VRPOrToolsSolver | 5220.90 | Global batch assignment ổn định |
| GreedyBFS | 4962.37 | Local policy nhanh và mạnh |
| MAPDCBSSolver | 4597.89 | Conflict avoidance rõ nhất |

MAPD-CBS không phải solver điểm cao nhất, nhưng có vai trò riêng: nó trực tiếp xử lý xung đột giữa nhiều agent. Greedy/VRP/ACO chọn task tốt hơn, nhưng conflict handling của chúng chỉ là resolve move một bước. MAPD-CBS có nền tảng tốt để mở rộng thành multi-step reservation hoặc CBS thật.

## 11. Kết luận

Pipeline MAPD-CBS:

1. `solver_baseline`: reservation một bước + nearest assignment, chứng minh khung conflict-aware chạy được.
2. `solvers`: thêm score-based assignment, delivery target, urgency priority, edge-swap check và smart wander. Đây là bước tăng điểm chính: `1263.66 -> 4597.89`.
3. `solvers_v1`: thêm sticky assignment, urgency scale và detour tolerance theo map. Public score giảm nhẹ `-33.63`, nên hướng này cần tune tiếp.

Kết luận kỹ thuật: MAPD-CBS có điểm mạnh về xử lý conflict, nhưng để cạnh tranh với ACO/VRP cần cải thiện assignment và lập kế hoạch nhiều bước. Bản hiện tại phù hợp để báo cáo như một hướng giải quyết khác: ưu tiên an toàn đường đi và tránh xung đột, chấp nhận tradeoff về reward so với các thuật toán assignment mạnh hơn.

