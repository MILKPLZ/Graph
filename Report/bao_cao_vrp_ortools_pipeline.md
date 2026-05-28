# Báo cáo thuật toán VRP/OR-Tools cho bài toán Multi-Agent Package Delivery

## 1. Bối cảnh thực tế

Trong hệ thống giao hàng đô thị, một quyết định quan trọng không chỉ là shipper đi đường nào, mà là đơn nào nên giao cho shipper nào. Nếu mỗi shipper tự chọn đơn gần nhất, nhiều shipper có thể cùng hướng về một vùng, trong khi các vùng khác bị bỏ trống. Hướng VRP giải quyết vấn đề này bằng cách nhìn toàn cục hơn: tại mỗi thời điểm, hệ thống tạo một bài toán phân công giữa shipper và đơn hàng đang visible.

Trong repo này, thuật toán `VRPOrToolsSolver` đại diện cho hướng Vehicle Routing Problem. Tên solver giữ ý tưởng VRP/OR-Tools, nhưng triển khai hiện tại là rolling-horizon global batch matching, không gọi trực tiếp thư viện OR-Tools. Đây là một lựa chọn thực dụng: giữ tinh thần tối ưu phân công của VRP, nhưng đủ nhẹ để chạy online mỗi timestep.

Điểm mạnh của hướng VRP là phối hợp nhiều shipper tốt hơn Greedy BFS. Thay vì từng shipper tự quyết định cục bộ, solver xây dựng score matrix cho toàn bộ cặp `(shipper, order)`, rồi chọn assignment không trùng shipper và không trùng order.

## 2. Phát biểu bài toán

Đầu vào:

- Bản đồ lưới `N x N` có ô trống và vật cản.
- `C` shipper, mỗi shipper có vị trí, tải trọng tối đa `W_max`, số đơn tối đa `K_max`.
- Tổng số đơn `G`, nhưng đơn được sinh/reveal online trong quá trình chạy.
- Mỗi đơn `o_i = (s_i, e_i, et_i, w_i, p_i)` gồm pickup, delivery, deadline, weight và priority.
- Horizon `T`.

Tại timestep `t`, solver phải chọn action cho từng shipper:

- Di chuyển `U/D/L/R/S`.
- Nhặt đơn nếu đứng tại pickup.
- Giao đơn nếu đứng tại delivery.

Mục tiêu:

```text
maximize net_reward = delivery_reward - movement_cost
```

Ràng buộc:

- Shipper chỉ di chuyển trên ô hợp lệ.
- Không vượt quá tải trọng và số đơn trong túi.
- Một đơn chỉ được một shipper nhận.
- Quyết định là online, chỉ dùng observation hiện tại.

## 3. Mô hình hóa toán học

Mô hình bản đồ thành đồ thị không trọng số:

```text
G_map = (V, E)
```

Trong đó `V` là tập ô đi được, `E` nối hai ô kề nhau theo 4 hướng. Khoảng cách ngắn nhất:

```text
d(u, v) = BFS_shortest_path(u, v)
```

Với shipper `k` và order `i`, độ dài route đơn giản để shipper nhận và giao order:

```text
route_len(k, i, t) = d(pos_k(t), pickup_i) + d(pickup_i, delivery_i)
```

Thời điểm giao ước lượng:

```text
arrival(k, i, t) = t + route_len(k, i, t)
```

Score assignment:

```text
score(k, i, t) = reward_estimate(i, arrival) / route_len
                 + urgency_bonus
                 + priority_bonus
                 + detour_bonus
                 + hotspot_bonus
```

Biến quyết định:

```text
x_{k,i} = 1 nếu shipper k được gán order i
x_{k,i} = 0 ngược lại
```

Bài toán assignment đơn giản tại timestep `t`:

```text
maximize Σ_k Σ_i score(k, i, t) * x_{k,i}
```

Với ràng buộc:

```text
Σ_i x_{k,i} <= 1       mỗi shipper nhận nhiều nhất một target pickup mới
Σ_k x_{k,i} <= 1       mỗi order được gán cho nhiều nhất một shipper
x_{k,i} = 0 nếu shipper k không thể mang order i
```

Đây không phải VRP đầy đủ nhiều điểm đến trong một route; nó là rolling-horizon assignment: cứ mỗi timestep lại cập nhật assignment theo trạng thái mới.

## 4. Baseline: `solver_baseline/vrp_ortools.py`

Baseline nằm ở:

```text
solver_baseline/vrp_ortools.py
```

Thiết kế baseline:

- Với mỗi timestep, duyệt mọi cặp `(shipper, order)` feasible.
- Tính khoảng cách BFS:

```text
shipper -> pickup -> delivery
```

- Tính score đơn giản:

```text
score = reward_estimate(order, t + route_len) / route_len
```

- Sắp xếp score giảm dần.
- Greedy matching: chọn cặp tốt nhất, bỏ qua nếu shipper hoặc order đã được dùng.
- Sau khi có assignment, shipper đi từng bước bằng BFS đến pickup; nếu túi đầy thì đi giao nearest delivery.

Điểm mạnh:

- Có phối hợp toàn cục cơ bản.
- Giảm hiện tượng nhiều shipper cùng chọn một đơn.
- Vẫn đơn giản, chạy nhanh và dễ debug.

Điểm yếu:

- Score reward còn thô, chưa dùng đầy đủ `delivery_reward`.
- Không có delivery target tối ưu khi shipper đang mang nhiều đơn.
- Chưa xét detour: shipper đang đi giao nhưng có thể tiện đường nhặt thêm đơn.
- Không có hotspot learning.
- Không có collision resolution chung như base solver nâng cao.
- Chưa tối ưu route nhiều điểm như VRP thật.

Kết quả baseline trên `test_config.txt`:

| Config | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ |
|---|---:|---:|---:|---:|---:|
| C1 | 266.56 | 13/15 | 13 | 0 | 2 |
| C2 | 418.85 | 24/25 | 21 | 3 | 1 |
| C3 | 401.93 | 15/40 | 15 | 0 | 25 |
| C4 | 681.12 | 50/60 | 32 | 18 | 10 |
| C5 | 1301.89 | 75/80 | 57 | 18 | 5 |
| C6 | 522.06 | 32/100 | 22 | 10 | 68 |

Tổng baseline:

- Net reward: `3592.41`
- Giao hàng: `209/320`
- Đúng hạn: `160`
- Trễ: `49`
- Bỏ lỡ: `111`

Baseline VRP tốt hơn baseline Greedy BFS vì đã có global assignment, nhưng vẫn yếu trên C3 và C6 do chưa có scoring/urgency/delivery logic đủ tốt.

## 5. Cải tiến: từ `solver_baseline` sang `solvers`

Bản cải tiến nằm ở:

```text
solvers/vrp_ortools.py
solvers/solver.py
```

### 5.1. Rolling-horizon global batch matching

Baseline đã có assignment mỗi timestep, nhưng score đơn giản. Bản cải tiến giữ cấu trúc rolling horizon:

1. Quan sát orders và shippers hiện tại.
2. Cập nhật delivery target cho shipper đang mang hàng.
3. Xây score matrix cho các order chưa được pick.
4. Greedy matching không trùng shipper/order.
5. Sinh action một bước bằng BFS.

Mục đích:

- Giữ bài toán online, không lập kế hoạch xa quá vì đơn tương lai chưa biết.
- Cập nhật assignment liên tục khi đơn mới xuất hiện hoặc shipper đã nhặt/giao đơn.

Tradeoff:

- Assignment có thể thay đổi mỗi step, gây thiếu ổn định mục tiêu.
- Nhưng trong môi trường online, re-plan thường tốt hơn giữ plan cũ khi trạng thái đã thay đổi.

### 5.2. Score pickup dùng reward thật

Bản cải tiến dùng `score_pickup()` trong `solvers/solver.py`, trong đó có:

- BFS distance từ shipper đến pickup.
- BFS distance từ pickup đến delivery.
- `delivery_reward(order, arrival, T)`.
- Efficiency theo reward/khoảng cách.
- Priority weight.
- Urgency theo slack deadline.
- Late factor nếu dự kiến giao trễ.
- Distance penalty.
- Hotspot bonus.

Mục đích:

- Assignment không chỉ dựa vào khoảng cách ngắn.
- Ưu tiên order có reward cao, deadline gấp, priority lớn.

Tradeoff:

- Score có nhiều heuristic nên cần kiểm soát overfit.
- Một order xa nhưng reward cao có thể được chọn, làm tăng rủi ro nếu đường thực tế qua bottleneck.

### 5.3. Delivery target cho shipper đang mang hàng

Bản cải tiến thêm `_delivery_targets`. Với shipper đang có bag, solver chọn destination tốt nhất bằng `best_delivery_dest()` thay vì chỉ giao nearest delivery.

Mục đích:

- Chọn điểm giao dựa trên reward/deadline, không chỉ khoảng cách.
- Nếu nhiều đơn cùng destination, cộng bonus để tận dụng gom giao.

Tradeoff:

- Có thể bỏ qua điểm gần hơn để đi điểm có score cao hơn.
- Nếu score delivery lệch, shipper có thể đi route dài hơn cần thiết.

### 5.4. Detour bonus

Nếu shipper đang có delivery target `dd`, một order mới có pickup gần `dd` sẽ được cộng bonus:

```text
if d(dd, pickup_o) < detour_thresh:
    bonus = 2.0
```

Mục đích:

- Mô phỏng ý tưởng VRP: đang đi tuyến giao hàng thì có thể nhận thêm đơn tiện đường.
- Tăng khả năng tận dụng capacity.

Tradeoff:

- Detour bonus cố định có thể quá lớn hoặc quá nhỏ tùy map.
- Nếu pickup gần delivery target nhưng delivery của order mới xa, route tổng vẫn có thể kém.

### 5.5. Urgency và fallback delivery

Trong `_decide_actions()`:

- Nếu có đơn trong bag sắp trễ, shipper ưu tiên đi delivery target.
- Nếu không còn assignment pickup hợp lệ, shipper chuyển sang giao đơn đang mang.
- Nếu không có gì tốt, dùng smart wander.

Mục đích:

- Tránh tình trạng cứ nhận thêm đơn trong khi bag có đơn gần deadline.
- Giảm thời gian chết khi assignment bị invalid sau khi order đã được shipper khác pick.

Tradeoff:

- Urgency threshold quá mạnh sẽ làm shipper giao sớm, giảm batching.
- Urgency quá yếu sẽ làm tăng late orders.

### 5.6. Collision resolution và smart wander

Bản cải tiến dùng `resolve_moves()` để giảm xung đột một bước giữa shippers. Khi không có target, shipper đi về vùng pending orders hoặc center hợp lệ thay vì đứng yên.

Mục đích:

- Giảm mất bước do nhiều shipper muốn vào cùng một ô.
- Tăng khả năng bắt đơn mới trong môi trường hotspot/surge.

Tradeoff:

- Collision handling vẫn là local one-step, không phải CBS đầy đủ.
- Smart wander dựa trên đơn/hotspot quan sát được, không bảo đảm đúng với tương lai.

Kết quả trên `test_config.txt`:

| Config | Baseline | `solvers/VRP` | Chênh lệch | Giao baseline | Giao cải tiến |
|---|---:|---:|---:|---:|---:|
| C1 | 266.56 | 264.34 | -2.22 | 13/15 | 13/15 |
| C2 | 418.85 | 432.22 | +13.37 | 24/25 | 24/25 |
| C3 | 401.93 | 864.91 | +462.99 | 15/40 | 36/40 |
| C4 | 681.12 | 1010.34 | +329.22 | 50/60 | 56/60 |
| C5 | 1301.89 | 1166.53 | -135.36 | 75/80 | 73/80 |
| C6 | 522.06 | 1482.56 | +960.50 | 32/100 | 91/100 |

Tổng:

- Baseline: `3592.41`
- `solvers/VRPOrToolsSolver`: `5220.90`
- Cải thiện: `+1628.49`
- Giao hàng: `209/320 -> 293/320`
- Đúng hạn: `160 -> 249`
- Bỏ lỡ: `111 -> 27`

Nhận xét quan trọng:

- Cải tiến rất mạnh ở C3 và C6, nơi baseline bị yếu do assignment/delivery đơn giản.
- C5 giảm `-135.36` dù số đơn giao vẫn cao. Đây là tradeoff của reward-aware/urgency/detour: không chỉ số đơn giao quyết định điểm, mà còn đúng hạn, priority, weight và chi phí di chuyển.

## 6. Final: từ `solvers` sang `solvers_v1`

Bản final nằm ở:

```text
solvers_v1/vrp_ortools.py
solvers_v1/solver.py
```

Trên `test_config.txt`, điểm public giữ nguyên:

```text
5220.90 -> 5220.90
```

Điều này cho thấy các thay đổi v1 được thiết kế có điều kiện để không phá điểm public nhỏ, đồng thời tăng generalization trên val configs lớn/khó.

### 6.1. Detour threshold có điều kiện

Bản `solvers` dùng:

```text
detour_thresh = max(3, N // 4)
bonus = 2.0
```

Bản `solvers_v1` dùng:

```text
use_generalized_detour = N > 20 or C > N
detour_thresh = max(3, N // 2) nếu generalized
detour_thresh = max(3, N // 4) nếu public/small map
bonus = max(0.5, score * 0.15) nếu generalized
bonus = 2.0 nếu small map
```

Mục đích:

- Trên map lớn, pickup tiện đường có thể cách delivery target xa hơn theo tuyệt đối nhưng vẫn hợp lý theo tỷ lệ map.
- Bonus tỷ lệ theo score tránh việc `+2.0` cố định quá nhỏ hoặc quá lớn.

Tradeoff:

- Tăng khả năng nhận thêm đơn tiện đường trên map lớn.
- Có rủi ro nhận detour quá nhiều nếu map lớn nhưng deadline gắt.

### 6.2. `_map_radius` trong shared solver

`solvers_v1/solver.py` thêm `_map_radius`, tính theo 90th-percentile BFS distance từ center hợp lệ. Các distance penalty dùng `_map_radius` thay vì chỉ dùng `N`.

Mục đích:

- Trên map nhiều obstacle hoặc bottleneck, khoảng cách shortest path thực tế không phản ánh đúng bằng kích thước `N`.
- VRP assignment cần distance normalization theo topology thật, không chỉ theo kích thước lưới.

Tradeoff:

- Cần thêm BFS để tính bán kính hiệu dụng.
- Trên public `N <= 20`, ảnh hưởng nhỏ nên điểm giữ nguyên.

### 6.3. Urgency và hotspot anti-overfit

Shared solver v1 thay đổi:

- Urgency multiplier giảm trên map `N > 20`.
- Hotspot bonus scale theo score trên map lớn/dense.

Mục đích:

- Tránh giao quá sớm trên map lớn khiến shipper không tận dụng capacity.
- Để hotspot có tác dụng tương đối với reward/distance trên map lớn.

Tradeoff:

- Nếu deadline cực chặt, giảm urgency có thể làm tăng late.
- Nếu hotspot quá nhiễu, shipper có thể bị kéo về vùng không còn tốt.

## 7. Thực nghiệm

### 7.1. Public test: `test_config.txt`

| Phiên bản | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ | Runtime tổng |
|---|---:|---:|---:|---:|---:|---:|
| `solver_baseline/VRPOrToolsSolver` | 3592.41 | 209/320 | 160 | 49 | 111 | ~2.21s |
| `solvers/VRPOrToolsSolver` | 5220.90 | 293/320 | 249 | 44 | 27 | ~0.87s |
| `solvers_v1/VRPOrToolsSolver` | 5220.90 | 293/320 | 249 | 44 | 27 | ~1.08s |

Public test cho thấy bước cải tiến chính là từ baseline sang `solvers`. Final v1 giữ nguyên public score.

### 7.2. Validation core4: generalization

Kết quả val core4 so sánh `solvers` và `solvers_v1`:

| Config | `solvers` | `solvers_v1` | Chênh lệch | Giao `solvers` | Giao `v1` |
|---|---:|---:|---:|---:|---:|
| V_TrafficJam | 6867.89 | 7453.77 | +585.88 | 439/500 | 461/500 |
| V_MediumSparse | 1168.20 | 2327.55 | +1159.34 | 92/300 | 198/300 |
| V_Maze | 299.94 | 373.56 | +73.62 | 18/800 | 47/800 |
| V_City | 1720.49 | 2023.43 | +302.94 | 294/1000 | 407/1000 |

Tổng val core4:

- `solvers`: `10056.53`
- `solvers_v1`: `12178.31`
- Chênh lệch: `+2121.78`
- Số đơn giao: `843 -> 1113`

Đây là lý do `solvers_v1` được xem là final cho hướng VRP: không tăng điểm public, nhưng cải thiện rõ generalization trên map lớn/khó.

## 8. Ablation study

Ablation theo mốc triển khai:

| Mốc | Thành phần chính | Public score | Giao/Tổng | Ý nghĩa |
|---|---|---:|---:|---|
| A0 | Baseline greedy assignment theo reward/distance | 3592.41 | 209/320 | Có global assignment nhưng scoring và routing còn thô |
| A1 | Reward-aware score, delivery target, urgency, detour bonus, smart wander, collision resolve | 5220.90 | 293/320 | Tăng mạnh chất lượng assignment và giảm missed orders |
| A2 | Detour generalized, `_map_radius`, hotspot/urgency anti-overfit | 5220.90 | 293/320 | Giữ public score, tăng val core4 từ 10056.53 lên 12178.31 |

Chi tiết public:

| Config | Baseline | Enhanced | Final v1 | Δ Enhanced-BL | Δ Final-Enhanced |
|---|---:|---:|---:|---:|---:|
| C1 | 266.56 | 264.34 | 264.34 | -2.22 | +0.00 |
| C2 | 418.85 | 432.22 | 432.22 | +13.37 | +0.00 |
| C3 | 401.93 | 864.91 | 864.91 | +462.99 | +0.00 |
| C4 | 681.12 | 1010.34 | 1010.34 | +329.22 | +0.00 |
| C5 | 1301.89 | 1166.53 | 1166.53 | -135.36 | +0.00 |
| C6 | 522.06 | 1482.56 | 1482.56 | +960.50 | +0.00 |

Phản biện:

- Baseline thắng enhanced ở C5 về net reward. Điều này cho thấy heuristic phức tạp không phải lúc nào cũng tốt trên từng config.
- Tuy nhiên enhanced thắng lớn trên tổng điểm và đặc biệt trên C6, nơi baseline bỏ lỡ 68/100 đơn.
- Final v1 không nên được đánh giá chỉ bằng public test vì các thay đổi của nó chủ yếu bật trên map lớn/khó. Val core4 cho thấy tradeoff này hợp lý.

## 9. Độ phức tạp

Ký hiệu:

- `V`: số ô trống.
- `E`: số cạnh hợp lệ, với grid 4-neighbor thì `E = O(V)`.
- `C`: số shipper.
- `M_t`: số order visible tại timestep `t`.
- `T`: số timestep.

### Baseline

Mỗi timestep, baseline duyệt mọi cặp shipper-order:

```text
O(C * M_t)
```

Mỗi cặp cần 2 truy vấn BFS distance. Nếu chưa cache:

```text
O(V + E) = O(V)
```

Sắp xếp candidates:

```text
O((C * M_t) log(C * M_t))
```

Tổng một timestep:

```text
O(C * M_t * V + (C * M_t) log(C * M_t))
```

### Bản cải tiến và final

Vẫn có cùng worst-case order, nhưng dùng BFS cache:

- `_dist_cache`
- `_parent_cache`
- `_next_move_cache`

Do đó runtime thực tế giảm khi nhiều truy vấn lặp lại. Ngoài ra, final v1 tính thêm `_map_radius` bằng một BFS từ center hợp lệ:

```text
O(V)
```

Chi phí này chỉ trả một lần lúc khởi tạo solver.

Bộ nhớ cache:

```text
O(S * V)
```

Trong đó `S` là số start position từng được BFS.

Tradeoff độ phức tạp:

- VRP assignment tốn hơn Greedy BFS vì phải xét toàn bộ ma trận shipper-order.
- Đổi lại, solver giảm trùng mục tiêu và tăng số đơn giao, đặc biệt khi `C` và `M_t` lớn.

## 10. So sánh với các thuật toán khác

Điểm trên `test_config.txt` của các solver hiện tại:

| Thuật toán | Tổng điểm | Vai trò/điểm mạnh |
|---|---:|---|
| ACOSolver | 5242.26 | Exploration trên assignment, có thể thoát local optimum |
| VRPOrToolsSolver | 5220.90 | Global batch assignment, cân bằng tốt giữa điểm và runtime |
| GreedyBFS | 4962.37 | Nhanh, đơn giản, policy cục bộ mạnh |
| MAPDCBSSolver | 4597.89 | Tập trung xử lý conflict multi-agent |

VRP đứng gần nhất với ACO và cao hơn Greedy BFS/MAPD-CBS trên public test. Điểm mạnh của VRP là global assignment rõ ràng: mỗi đơn và mỗi shipper được phối hợp trong cùng một score matrix. So với ACO, VRP ít ngẫu nhiên hơn và dễ giải thích hơn. So với Greedy BFS, VRP giảm trùng mục tiêu. So với MAPD-CBS, VRP chọn task tốt hơn nhưng xử lý conflict kém sâu hơn.

## 11. Kết luận

Pipeline phát triển VRP/OR-Tools có thể tóm tắt:

1. `solver_baseline`: greedy matching đơn giản theo reward/distance, chứng minh hướng global assignment có hiệu quả.
2. `solvers`: thêm reward-aware scoring, urgency, delivery target, detour bonus, smart wander và collision resolve. Đây là bước tăng public score chính: `3592.41 -> 5220.90`.
3. `solvers_v1`: thêm generalized detour, `_map_radius`, hotspot/urgency anti-overfit. Public score giữ nguyên, nhưng val core4 tăng `+2121.78`.

Vì vậy, VRP là hướng giải quyết cân bằng nhất giữa tối ưu toàn cục và runtime online. Nó không cố giải VRP đầy đủ nhiều điểm bằng solver nặng, mà dùng rolling-horizon assignment để phù hợp với môi trường đơn hàng reveal theo thời gian. Tradeoff này giúp thuật toán vừa nhanh, vừa đạt điểm cao, vừa generalize tốt hơn trên map lớn.

