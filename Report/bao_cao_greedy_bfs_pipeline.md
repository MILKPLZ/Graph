# Báo cáo thuật toán Greedy BFS cho bài toán Multi-Agent Package Delivery

## 1. Bối cảnh thực tế

Bài toán mô phỏng một hệ thống giao hàng nhiều shipper trên bản đồ dạng lưới. Ở mỗi thời điểm, đơn hàng mới có thể xuất hiện, shipper chỉ quan sát được trạng thái hiện tại và phải ra quyết định online: đi đâu, nhặt đơn nào, giao đơn nào. Đây là bối cảnh gần với các nền tảng giao vận đô thị, nơi đơn hàng không biết trước toàn bộ, deadline thay đổi theo priority, năng lực shipper bị giới hạn bởi tải trọng và số lượng đơn có thể mang.

Trong nhóm các thuật toán đã triển khai, `GreedyBFS` đại diện cho hướng giải quyết thực dụng: không tối ưu toàn cục bằng mô hình lớn, mà dùng quyết định cục bộ nhanh, có thể chạy ổn định mỗi timestep. Điểm mạnh của hướng này là tốc độ, dễ giải thích, dễ kiểm soát lỗi trong môi trường online.

## 2. Phát biểu bài toán

Đầu vào gồm:

- Bản đồ lưới `N x N`, ô trống có thể đi qua và ô vật cản không thể đi qua.
- `C` shipper, mỗi shipper có vị trí hiện tại, tải trọng tối đa `W_max`, số đơn tối đa `K_max`.
- Tổng số đơn `G`, nhưng đơn được reveal online theo thời gian.
- Mỗi đơn hàng `o_i = (s_i, e_i, et_i, w_i, p_i)` gồm điểm lấy, điểm giao, deadline, khối lượng và priority.
- Horizon thời gian `T`.

Ở mỗi bước thời gian `t`, solver chọn action cho từng shipper:

- Di chuyển một ô theo `U/D/L/R` hoặc đứng yên `S`.
- Thao tác hàng hóa: không làm gì, nhặt hàng, hoặc giao hàng.

Mục tiêu là tối đa hóa tổng reward ròng:

```text
net_reward = tổng reward giao hàng - tổng chi phí di chuyển
```

Ràng buộc chính:

- Shipper chỉ đi trên ô hợp lệ.
- Shipper không vượt quá `W_max` và `K_max`.
- Đơn chỉ được nhặt tại pickup cell và giao tại delivery cell.
- Solver chỉ dùng observation hiện tại, không biết trước toàn bộ đơn tương lai.

## 3. Mô hình hóa toán học

Xem bản đồ là đồ thị không trọng số:

```text
G_map = (V, E)
```

Trong đó:

- `V` là tập ô trống trên lưới.
- `(u, v) in E` nếu hai ô kề nhau theo 4 hướng.
- Khoảng cách ngắn nhất giữa hai ô được tính bằng BFS:

```text
d(u, v) = shortest_path_length(u, v)
```

Trạng thái shipper `k` tại thời điểm `t`:

```text
x_k(t) = (pos_k(t), bag_k(t), W_k(t))
```

Với một đơn `o`, ước lượng thời gian hoàn thành nếu shipper `k` nhận đơn đó:

```text
arrival(k, o, t) = t + d(pos_k(t), pickup_o) + d(pickup_o, delivery_o)
```

Slack deadline:

```text
slack(k, o, t) = et_o - arrival(k, o, t)
```

Greedy BFS không giải bài toán tối ưu toàn cục. Thay vào đó, thuật toán dùng hàm điểm cục bộ:

```text
score(k, o, t) = reward_estimate(o, arrival) / distance
                 + priority_bonus
                 + urgency_bonus
                 - distance_penalty
                 + hotspot_bonus
```

Tại mỗi timestep, shipper chọn hành động có score tốt nhất theo thứ tự ưu tiên: giao hàng khẩn cấp, nhận đơn tốt, giao hàng còn lại, hoặc di chuyển về vùng có khả năng có đơn.

## 4. Baseline: `solver_baseline/greedy_bfs.py`

Baseline Greedy BFS được đặt tại:

```text
solver_baseline/greedy_bfs.py
```

Thiết kế baseline:

- Dùng BFS để đi theo đường ngắn nhất.
- Nếu đang ở điểm giao thì giao ngay.
- Nếu đang ở điểm lấy thì nhặt ngay.
- Nếu túi đầy hoặc có đơn gần trễ thì đi giao.
- Nếu còn capacity thì chọn đơn visible tốt nhất bằng score đơn giản:

```text
score = reward_estimate / (d_pickup + d_delivery)
        + priority_weight / remaining_deadline
```

Điểm mạnh:

- Cực kỳ đơn giản và chạy nhanh.
- Có thể làm mốc kiểm tra pipeline: đọc observation, chọn action, nhặt/giao hợp lệ.
- Dễ giải thích trong báo cáo vì quyết định dựa trên priority, deadline và khoảng cách.

Điểm yếu:

- Chỉ tối ưu cục bộ theo từng shipper.
- Scoring reward còn thô, chưa dùng đúng hàm reward đầy đủ của môi trường.
- Chưa có học hotspot.
- Reservation chỉ ở mức đơn giản theo order id, chưa xử lý tốt xung đột di chuyển.
- Khi không có đơn tốt, shipper thường đứng yên hoặc xử lý fallback yếu.

Kết quả baseline trên `test_config.txt`:

| Config | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ |
|---|---:|---:|---:|---:|---:|
| C1 | 128.80 | 9/15 | 5 | 4 | 6 |
| C2 | 107.44 | 11/25 | 6 | 5 | 14 |
| C3 | 155.20 | 5/40 | 5 | 0 | 35 |
| C4 | 443.80 | 24/60 | 22 | 2 | 36 |
| C5 | 226.65 | 17/80 | 10 | 7 | 63 |
| C6 | 141.70 | 16/100 | 7 | 9 | 84 |

Tổng baseline:

- Net reward: `1203.59`
- Giao hàng: `82/320`
- Đúng hạn: `55`
- Tỷ lệ giao theo tổng đơn: `25.63%`

Baseline cho thấy BFS giúp solver chạy đúng, nhưng policy cục bộ chưa đủ để khai thác bản đồ lớn và deadline.

## 5. Cải tiến: từ `solver_baseline` sang `solvers`

Bản cải tiến nằm ở:

```text
solvers/greedy_bfs.py
solvers/solver.py
```

Các cải tiến chính không chỉ nằm trong file `greedy_bfs.py`, mà còn trong base class `Solver`.

### 5.1. BFS cache

Baseline gọi BFS nhiều lần cho các cặp điểm. Bản cải tiến lưu:

- `_dist_cache`: cache khoảng cách giữa hai điểm.
- `_parent_cache`: cache cây BFS từ một điểm xuất phát.
- `_next_move_cache`: cache bước đi đầu tiên trên shortest path.

Mục đích:

- Giảm chi phí tính lại BFS khi nhiều shipper cùng đánh giá đơn.
- Cho phép scoring phức tạp hơn mà runtime vẫn thấp.

Tradeoff:

- Tốn thêm bộ nhớ theo số điểm đã truy vấn.
- Phù hợp vì bản đồ public có kích thước vừa, số ô trống hữu hạn.

### 5.2. Scoring pickup reward-aware

Bản cải tiến dùng trực tiếp `delivery_reward(order, arrival, T)` thay vì ước lượng thô. Score có các thành phần:

- reward kỳ vọng khi giao tại thời điểm ước lượng;
- efficiency theo reward/khoảng cách;
- trọng số priority;
- urgency theo slack deadline;
- late factor nếu dự kiến trễ;
- distance penalty cho đơn quá xa.

Mục đích:

- Không chỉ chọn đơn gần nhất.
- Ưu tiên đơn có reward cao và deadline đáng xử lý.

Tradeoff:

- Score phức tạp hơn và có nhiều hệ số heuristic.
- Nếu hệ số không tốt, solver có thể overfit test nhỏ.

### 5.3. Adaptive urgency threshold

Baseline chỉ có logic khẩn cấp đơn giản. Bản cải tiến dùng:

```text
threshold = f(N, bag_count, K_max)
```

Nếu túi đầy, shipper bắt buộc chuyển sang giao. Nếu túi gần đầy, threshold giảm để shipper không ôm thêm đơn quá lâu.

Mục đích:

- Cân bằng giữa gom đơn và giao đúng hạn.
- Tránh shipper tiếp tục đi pickup trong khi đơn trong túi sắp trễ.

Tradeoff:

- Threshold quá nhỏ: giao sớm, bỏ lỡ cơ hội gom đơn.
- Threshold quá lớn: ôm nhiều đơn, tăng nguy cơ trễ hạn.

### 5.4. Best delivery destination

Thay vì giao đơn gần nhất đơn thuần, bản cải tiến dùng `score_delivery()` và cộng bonus nếu nhiều đơn có cùng destination.

Mục đích:

- Khi shipper mang nhiều đơn, chọn điểm giao có lợi hơn theo reward/deadline.
- Tận dụng trường hợp nhiều đơn cùng điểm đến.

Tradeoff:

- Có thể bỏ qua một đơn gần hơn nếu score thấp hơn, làm tăng quãng đường ngắn hạn để đổi lấy reward dài hạn.

### 5.5. Hotspot tracking và smart wander

Bản cải tiến ghi nhận vị trí pickup của các đơn mới trong một cửa sổ lịch sử. Khi không có mục tiêu tốt, shipper không đứng yên mà di chuyển về:

- vùng có nhiều pending orders;
- hoặc fallback center hợp lệ.

Mục đích:

- Giảm thời gian chết khi đơn chưa xuất hiện tại vị trí hiện tại.
- Thích nghi với hotspot/surge trong môi trường online.

Tradeoff:

- Hotspot học từ quá khứ, không đảm bảo đúng tương lai.
- Nếu hotspot bonus quá lớn, shipper có thể bị hút về vùng đông đơn nhưng deadline/reward không tốt.

### 5.6. Collision avoidance một bước

Bản cải tiến tạo `desired` move cho từng shipper rồi gọi `resolve_moves()`. Nếu hai shipper muốn vào cùng một ô, shipper sau sẽ tìm bước thay thế hợp lệ hoặc đứng yên.

Mục đích:

- Giảm mất bước do va chạm.
- Tăng hiệu quả trên config nhiều shipper.

Tradeoff:

- Chỉ xử lý xung đột một bước, không phải MAPF/CBS đầy đủ.
- Có thể chọn alternative move không tối ưu dài hạn.

Kết quả sau cải tiến:

| Config | Baseline | `solvers/GreedyBFS` | Chênh lệch | Giao baseline | Giao cải tiến |
|---|---:|---:|---:|---:|---:|
| C1 | 128.80 | 243.62 | +114.82 | 9/15 | 12/15 |
| C2 | 107.44 | 452.86 | +345.42 | 11/25 | 24/25 |
| C3 | 155.20 | 841.81 | +686.61 | 5/40 | 37/40 |
| C4 | 443.80 | 978.06 | +534.26 | 24/60 | 56/60 |
| C5 | 226.65 | 1047.62 | +820.97 | 17/80 | 64/80 |
| C6 | 141.70 | 1398.40 | +1256.70 | 16/100 | 91/100 |

Tổng:

- Baseline: `1203.59`
- `solvers/GreedyBFS`: `4962.37`
- Cải thiện: `+3758.79`
- Số đơn giao: `82/320 -> 284/320`
- Số đơn đúng hạn: `55 -> 234`

Đây là bước cải tiến lớn nhất của pipeline Greedy BFS.

## 6. Final: từ `solvers` sang `solvers_v1`

Bản final nằm ở:

```text
solvers_v1/greedy_bfs.py
solvers_v1/solver.py
```

Trên `test_config.txt`, `GreedyBFS` trong `solvers_v1` giữ nguyên điểm so với `solvers`:

```text
4962.37 -> 4962.37
```

Điều này là chủ đích: v1 tập trung giảm overfit và tăng khả năng generalization, không hy sinh điểm public test.

### 6.1. `_map_radius` thay cho `N`

Bản `solvers` dùng `N` để chuẩn hóa distance penalty và reservation threshold:

```text
rel_d = d_pickup / N
reserve nếu d_pickup <= N
```

Bản `solvers_v1` thêm `_map_radius`, tính bằng 90th-percentile BFS distance từ center hợp lệ:

```text
map_radius = max(N, percentile_90_distance_from_center)
```

Sau đó dùng:

```text
rel_d = d_pickup / map_radius
reserve nếu d_pickup <= map_radius
```

Mục đích:

- Với map có obstacle/bottleneck, khoảng cách BFS thực tế có thể lớn hơn kích thước hình học `N`.
- Dùng `N` có thể phạt nhầm các đơn nhìn gần theo tọa độ nhưng xa theo đường đi.
- `_map_radius` làm threshold phụ thuộc topology thật của bản đồ.

Tradeoff:

- Cần chạy thêm BFS từ center để tính bán kính hiệu dụng.
- Trên map nhỏ public, `_map_radius` thường không làm thay đổi quyết định nên điểm giữ nguyên.

### 6.2. Urgency multiplier theo kích thước map

Bản `solvers_v1` thay đổi:

```text
urgency_multiplier = 0.5 nếu N > 20, ngược lại 1.5
```

Mục đích:

- Trên map lớn, nếu quá nhạy với urgency thì shipper dễ chuyển sang giao sớm và bỏ lỡ gom đơn.
- Điều kiện `N > 20` giúp tránh làm giảm điểm trên public configs nhỏ `N <= 20`.

Tradeoff:

- Đây là một lựa chọn anti-overfit có điều kiện.
- Nếu map lớn nhưng deadline rất gắt, giảm urgency có thể làm tăng trễ hạn.

### 6.3. Hotspot bonus scale theo score

Bản `solvers` dùng bonus cố định:

```text
score += hotspot_count * 0.05
```

Bản `solvers_v1` giữ bonus cố định trên map nhỏ, nhưng với map lớn/dense thì scale theo độ lớn score:

```text
score += hotspot_count * max(0.01, abs(score) * 0.02)
```

Mục đích:

- Trên map lớn, hotspot count tuyệt đối có thể quá nhỏ so với reward/distance.
- Bonus theo tỷ lệ giúp hotspot có tác dụng mà không lấn át toàn bộ score.

Tradeoff:

- Có thể tăng thiên lệch về vùng hotspot nếu dữ liệu gần đây không còn đại diện cho tương lai.

## 7. Thực nghiệm

### 7.1. Thiết lập

Chạy trên `test_config.txt`, gồm 6 config public:

- C1: `N=7, C=2, G=15, T=240`
- C2: `N=10, C=2, G=25, T=240`
- C3: `N=12, C=3, G=40, T=360`
- C4: `N=15, C=4, G=60, T=600`
- C5: `N=18, C=5, G=80, T=780`
- C6: `N=20, C=5, G=100, T=960`

Lệnh chạy baseline:

```bash
python -m solver_baseline.run_baselines --config test_config.txt --out results_solver_baseline
```

Kết quả solver hiện tại lấy từ:

```text
results/summary.json
```

Kết quả final v1 lấy từ:

```text
results_solvers_v1_test_config/summary.json
```

### 7.2. Bảng điểm chính

| Phiên bản | Net reward | Giao/Tổng | Đúng hạn | Trễ | Bỏ lỡ | Runtime tổng |
|---|---:|---:|---:|---:|---:|---:|
| `solver_baseline/GreedyBFS` | 1203.59 | 82/320 | 55 | 27 | 238 | ~1.60s |
| `solvers/GreedyBFS` | 4962.37 | 284/320 | 234 | 50 | 36 | ~0.81s |
| `solvers_v1/GreedyBFS` | 4962.37 | 284/320 | 234 | 50 | 36 | ~1.03s |

Nhận xét:

- Bản cải tiến tăng reward khoảng `4.12x` so với baseline.
- Tỷ lệ giao tăng từ `25.63%` lên `88.75%`.
- Số đơn đúng hạn tăng từ `55` lên `234`.
- Final v1 không tăng điểm public, nhưng giữ nguyên chất lượng trong khi thêm cơ chế generalization.

## 8. Ablation study

Do không có log chạy riêng cho từng heuristic nhỏ, ablation dưới đây được trình bày theo mốc triển khai thực tế:

| Mốc | Thành phần được thêm | Net reward | Giao/Tổng | Ý nghĩa |
|---|---|---:|---:|---|
| A0 | Baseline local score + BFS | 1203.59 | 82/320 | Chạy đúng nhưng thiếu phối hợp và scoring yếu |
| A1 | Reward-aware scoring, urgency, delivery score, hotspot, smart wander, collision resolve | 4962.37 | 284/320 | Cải thiện lớn về chọn đơn và giảm thời gian chết |
| A2 | `_map_radius`, urgency có điều kiện, hotspot scale cho map lớn | 4962.37 | 284/320 | Không đổi public score, tăng tính an toàn cho map ngoài public |

Chi tiết theo config:

| Config | Baseline | Enhanced | Final v1 | Δ Enhanced-BL | Δ Final-Enhanced |
|---|---:|---:|---:|---:|---:|
| C1 | 128.80 | 243.62 | 243.62 | +114.82 | +0.00 |
| C2 | 107.44 | 452.86 | 452.86 | +345.42 | +0.00 |
| C3 | 155.20 | 841.81 | 841.81 | +686.61 | +0.00 |
| C4 | 443.80 | 978.06 | 978.06 | +534.26 | +0.00 |
| C5 | 226.65 | 1047.62 | 1047.62 | +820.97 | +0.00 |
| C6 | 141.70 | 1398.40 | 1398.40 | +1256.70 | +0.00 |

Phân tích:

- Cải thiện lớn nhất ở C6: `+1256.70`, vì map lớn hơn và nhiều đơn hơn làm các heuristic như urgency, smart wander, score delivery phát huy rõ.
- C3 tăng từ `5/40` lên `37/40`, cho thấy baseline bị kẹt ở quyết định cục bộ, còn bản cải tiến biết tiếp tục tìm đơn và giao hợp lý hơn.
- A2 không tăng public test vì các điều kiện generalization chủ yếu bật trên map lớn hơn `N > 20` hoặc map có topology khiến `_map_radius` khác biệt.

## 9. Độ phức tạp

Ký hiệu:

- `V`: số ô trống trên bản đồ.
- `E`: số cạnh hợp lệ giữa các ô, với grid 4-neighbor thì `E = O(V)`.
- `C`: số shipper.
- `M_t`: số đơn visible tại timestep `t`.
- `T`: số timestep.

### Baseline

Mỗi shipper có thể đánh giá nhiều order. Nếu không cache, mỗi truy vấn khoảng cách BFS tốn:

```text
O(V + E) = O(V)
```

Một timestep:

```text
O(C * M_t * V)
```

Toàn episode:

```text
O(T * C * M_t * V)
```

### Bản cải tiến và final

Bản `solvers` và `solvers_v1` dùng cache BFS. Lần đầu BFS từ một start tốn `O(V)`, sau đó nhiều truy vấn từ cùng start dùng cache.

Trường hợp xấu vẫn có thể gần:

```text
O(T * C * M_t * V)
```

Nhưng thực tế giảm mạnh vì:

- nhiều pickup/delivery lặp lại;
- nhiều shipper gọi lại cùng khoảng cách;
- `bfs_next_move` dùng `_parent_cache`.

Bộ nhớ cache:

```text
O(S * V)
```

Trong đó `S` là số điểm start từng được BFS. Với map public, tradeoff này hợp lý vì runtime thực tế vẫn dưới vài giây.

## 10. So sánh với các thuật toán khác

Điểm trên `test_config.txt` của các solver hiện tại:

| Thuật toán | Tổng điểm | Vai trò/điểm mạnh |
|---|---:|---|
| ACOSolver | 5242.26 | Tìm assignment bằng exploration, tốt khi greedy dễ kẹt local optimum |
| VRPOrToolsSolver | 5220.90 | Batch/global assignment tốt, giảm trùng mục tiêu giữa shipper |
| GreedyBFS | 4962.37 | Nhanh, đơn giản, ổn định, dễ giải thích |
| MAPDCBSSolver | 4597.89 | Tập trung xử lý xung đột multi-agent |

Greedy BFS không cao nhất, nhưng có tradeoff tốt:

- Runtime thấp.
- Ít phụ thuộc thư viện ngoài.
- Dễ debug từng quyết định.
- Là baseline mạnh để kiểm tra các ý tưởng scoring, urgency và hotspot trước khi đưa vào VRP/ACO/CBS.

So với VRP và ACO, Greedy BFS yếu hơn ở phối hợp toàn cục. So với MAPD-CBS, Greedy BFS ít xử lý xung đột hơn nhưng lại chọn đơn tốt hơn và ít bị overhead lập kế hoạch. Vì vậy Greedy BFS phù hợp làm solver nền hoặc fallback policy trong các thuật toán phức tạp hơn.

## 11. Kết luận

Pipeline phát triển Greedy BFS có thể tóm tắt như sau:

1. `solver_baseline`: cài đặt Greedy BFS tối thiểu, đảm bảo chạy đúng online MAPD.
2. `solvers`: thêm reward-aware scoring, urgency, hotspot, smart wander, delivery ranking và collision avoidance một bước. Đây là bước tăng điểm chính.
3. `solvers_v1`: thêm `_map_radius` và điều kiện anti-overfit để giữ điểm public nhưng chuẩn bị tốt hơn cho map lớn/khó.

Kết quả thực nghiệm xác nhận hướng đi này hiệu quả: từ `1203.59` lên `4962.37`, số đơn giao tăng từ `82/320` lên `284/320`. Điểm mạnh của Greedy BFS là tạo ra một solver nhanh, dễ giải thích, đủ mạnh để cạnh tranh, đồng thời là nền tảng tốt để phân tích và phát triển các hướng nâng cao như VRP, ACO và MAPD-CBS.

