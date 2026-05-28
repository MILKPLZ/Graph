# Báo cáo đánh giá solver trên `test_config.txt`

## 1. Thiết lập chạy thử

- Ngày chạy: 2026-05-28
- Config: `test_config.txt`
- Seed gốc: `42`
- Chế độ bài toán: online MAPD, đơn hàng được reveal dần theo thời gian
- Lệnh chạy:

```bash
python3 run_test.py --config test_config.txt --out results_test_config_eval --method all
```

Kết quả chi tiết đã được lưu tại:

- `results_test_config_eval/summary.json`
- `results_test_config_eval/all_results.json`
- `results_test_config_eval/result_C1.json` ... `result_C6.json`

Tổng thời gian chạy tất cả thuật toán trên 6 config là `4.72s`.

## 2. Bảng điểm theo config

| Config | GreedyBFS | VRPOrToolsSolver | ACOSolver | MAPDCBSSolver | Thuật toán tốt nhất |
|---|---:|---:|---:|---:|---|
| C1 | 243.62 | 264.34 | 264.34 | **265.24** | MAPDCBSSolver |
| C2 | **452.86** | 432.22 | 446.83 | 429.45 | GreedyBFS |
| C3 | 841.81 | 864.91 | 863.92 | **873.76** | MAPDCBSSolver |
| C4 | 978.06 | 1010.34 | 973.98 | **1012.02** | MAPDCBSSolver |
| C5 | 1047.62 | 1166.53 | 1214.42 | **1245.21** | MAPDCBSSolver |
| C6 | 1398.40 | **1482.56** | 1478.79 | 772.21 | VRPOrToolsSolver |

Nhận xét nhanh:

- `ACOSolver` có tổng điểm cao nhất toàn bộ test.
- `VRPOrToolsSolver` đứng rất sát `ACOSolver`, chỉ kém khoảng `21.36` điểm.
- `MAPDCBSSolver` thắng nhiều config nhất, nhưng tụt mạnh ở C6 nên tổng điểm thấp.
- `GreedyBFS` là baseline ổn định, chạy nhanh, nhưng thua rõ trên các config lớn C5 và C6.

## 3. Thống kê tổng hợp

| Thuật toán | Tổng điểm | Giao/Tổng | Tỉ lệ giao | Đúng hạn | Trễ | Bỏ lỡ | Tỉ lệ đúng hạn trên đơn đã giao | Move cost | Wall time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ACOSolver | **5242.26** | 295/320 | **92.19%** | 243 | 52 | **25** | 82.37% | -120.55 | 1.31s |
| VRPOrToolsSolver | 5220.90 | 293/320 | 91.56% | **249** | **44** | 27 | **84.98%** | -124.61 | 1.13s |
| GreedyBFS | 4962.37 | 284/320 | 88.75% | 234 | 50 | 36 | 82.39% | -124.81 | **1.10s** |
| MAPDCBSSolver | 4597.89 | 279/320 | 87.19% | 205 | 74 | 41 | 73.48% | **-83.08** | 1.18s |

Xếp hạng tổng điểm:

1. `ACOSolver`: `5242.26`
2. `VRPOrToolsSolver`: `5220.90`
3. `GreedyBFS`: `4962.37`
4. `MAPDCBSSolver`: `4597.89`

## 4. Đánh giá từng thuật toán

### 4.1. GreedyBFS

Điểm tổng: `4962.37`

Ưu điểm:

- Cài đặt đơn giản, dễ kiểm soát và dễ debug.
- Chạy nhanh nhất trong lần thử này.
- Dùng BFS nên đi được trên bản đồ có vật cản, không phụ thuộc khoảng cách Manhattan thô.
- Có logic ưu tiên giao ngay nếu đang ở điểm đích.
- Hoạt động ổn định trên cả 6 config, không có config bị sụp điểm nghiêm trọng.

Nhược điểm:

- Quyết định còn thiên về cục bộ theo từng shipper.
- Không tối ưu phân công toàn cục, nên nhiều shipper vẫn có thể cạnh tranh các đơn gần giống nhau.
- Trên config lớn C5, C6, số đơn bỏ lỡ cao hơn VRP và ACO.
- Chưa khai thác tốt bài toán gom đơn theo route dài hạn.

Hướng cài đặt cụ thể:

1. Kế thừa `Solver` trong `solvers/solver.py`.
2. Trong `run()`, gọi `obs = env.reset()`, sau đó lặp `env.step(actions)` tới khi `done`.
3. Dùng `bfs_distance()` và `bfs_next_move()` để tìm đường ngắn nhất từ shipper tới pickup hoặc delivery.
4. Ở mỗi timestep, với từng shipper:
   - nếu đang đứng tại destination của đơn trong bag thì trả action `("S", 2)`;
   - nếu bag đầy hoặc có đơn sắp trễ thì đi tới delivery tốt nhất;
   - nếu còn sức chứa thì chọn pickup có `score_pickup()` cao nhất;
   - nếu không có việc thì `smart_wander_target()` tới vùng có đơn pending hoặc trung tâm hợp lệ.
5. Sau khi có move mong muốn, dùng `resolve_moves()` để giảm collision.
6. Dùng `choose_cargo_op()` để tự động chọn pickup/delivery tại ô sau khi di chuyển.

Nâng cấp nên làm:

- Thêm điểm thưởng cho đơn có pickup/delivery gần route hiện tại.
- Khi shipper đã có hàng, chỉ nhận thêm đơn nếu detour không làm trễ đơn đang mang.
- Dùng reservation theo nhiều bước thay vì chỉ resolve bước kế tiếp.

### 4.2. VRPOrToolsSolver

Điểm tổng: `5220.90`

Ưu điểm:

- Điểm tổng đứng thứ 2 và rất sát `ACOSolver`.
- Giao đúng hạn nhiều nhất: `249` đơn đúng hạn.
- Tỉ lệ đúng hạn trên đơn đã giao cao nhất: `84.98%`.
- C6 đạt điểm cao nhất trong tất cả thuật toán, cho thấy batch assignment hợp với bản đồ lớn.
- Cách chạy vẫn nhanh, chỉ hơn Greedy không đáng kể.

Nhược điểm:

- File tên là `vrp_ortools.py`, nhưng implementation hiện tại là VRP-like heuristic, chưa thật sự gọi OR-Tools.
- Chỉ phân công mỗi shipper một đơn mục tiêu ở mỗi lần re-plan, chưa tối ưu toàn route nhiều điểm.
- Matching hiện tại là greedy trên score matrix, chưa đảm bảo tối ưu toàn cục như Hungarian/min-cost matching.
- Có thể kém Greedy trên C2 do phân công batch làm mất vài deadline cục bộ.

Hướng cài đặt cụ thể:

1. Kế thừa `Solver`.
2. Duy trì hai map nội bộ:
   - `_assignments: shipper_id -> order_id` cho pickup target;
   - `_delivery_targets: shipper_id -> destination` cho đơn đang mang.
3. Mỗi timestep gọi `_batch_assign(obs)`:
   - lấy các order visible, chưa pickup, chưa delivered;
   - với mỗi shipper còn capacity, tính `score_pickup(shipper, order, t, orders)`;
   - cộng bonus nếu pickup nằm gần delivery target hiện tại;
   - sort các cặp `(score, shipper, order)` giảm dần;
   - chọn từng cặp sao cho một shipper không nhận nhiều hơn một order và một order không bị nhiều shipper đuổi.
4. Trong `_decide_actions()`:
   - giao ngay nếu có thể;
   - nếu đơn trong bag gấp, đi delivery;
   - nếu có assignment hợp lệ, đi pickup;
   - nếu không, giao đơn không gấp hoặc wander.
5. Kết thúc bằng `env.result("VRPOrToolsSolver", elapsed_sec)`.

Nếu muốn dùng OR-Tools thật:

1. Cài dependency trong môi trường cho phép:

```bash
python3 -m pip install ortools
```

2. Tại mỗi timestep, xây node gồm vị trí shipper, pickup visible và delivery liên quan.
3. Dùng BFS distance làm cost matrix thay vì Manhattan.
4. Thêm constraint capacity theo `K_max` và `W_max`.
5. Chỉ lấy action đầu tiên của route tối ưu, sau đó timestep sau re-plan lại vì bài toán online.
6. Vẫn cần fallback heuristic nếu OR-Tools không có sẵn trong môi trường chấm.

### 4.3. ACOSolver

Điểm tổng: `5242.26`

Ưu điểm:

- Tổng điểm cao nhất.
- Giao nhiều đơn nhất: `295/320`.
- Bỏ lỡ ít nhất: `25` đơn.
- Tốt trên C5 và C6, tức là tận dụng exploration tốt hơn Greedy khi không gian lớn.
- Có greedy baseline bên trong nên không bị phụ thuộc hoàn toàn vào random search.

Nhược điểm:

- Chạy chậm nhất trong lần thử, dù vẫn rất nhanh với Phase 1.
- ACO hiện chỉ tối ưu assignment ngắn hạn, chưa xây route nhiều điểm đầy đủ.
- Random seed đang cố định nội bộ bằng `random.Random(42)`, ổn định nhưng có thể overfit seed Phase 1.
- Tỉ lệ đúng hạn thấp hơn VRP do ACO ưu tiên giao nhiều đơn hơn, đôi khi nhận thêm đơn làm tăng trễ.

Hướng cài đặt cụ thể:

1. Kế thừa `Solver`.
2. Tạo pheromone table dạng `_pheromone[(shipper_id, order_id)] = value`.
3. Chọn tham số thích nghi theo kích thước bài:
   - `_aco_interval`: số bước mới chạy ACO một lần;
   - `_num_ants`: số ant;
   - `_num_iter`: số vòng lặp;
   - `_candidate_k`: số đơn ứng viên tốt nhất.
4. Ở mỗi timestep:
   - cập nhật delivery target cho shipper đang mang hàng;
   - tạo assignment greedy làm baseline;
   - nếu đến interval ACO, lấy top candidate order theo priority/reward;
   - mỗi ant xây assignment bằng xác suất `pheromone * heuristic`;
   - đánh giá assignment bằng reward dự kiến pickup rồi delivery;
   - bay hơi pheromone bằng `_evaporate()`;
   - deposit pheromone cho assignment tốt nhất bằng `_deposit()`.
5. Dùng assignment tốt nhất để điều khiển shipper tương tự VRP:
   - delivery gấp trước;
   - pickup theo assignment;
   - delivery thường;
   - wander.
6. Giới hạn ứng viên và số ant để không vượt runtime khi config lớn.

Nâng cấp nên làm:

- Đánh giá route nhiều pickup/delivery thay vì chỉ cặp shipper-order.
- Penalize assignment nếu làm đơn đang trong bag trễ deadline.
- Tự điều chỉnh `rho`, số ant và candidate size theo mật độ đơn visible, không chỉ theo `G`.

### 4.4. MAPDCBSSolver

Điểm tổng: `4597.89`

Ưu điểm:

- Thắng C1, C3, C4, C5 theo net reward.
- Move cost thấp nhất về độ âm: `-83.08`, tức là di chuyển ít hơn đáng kể.
- Có xử lý conflict tốt hơn Greedy/VRP ở mức một bước: reservation cell và kiểm tra edge-swap.
- Phù hợp với bản đồ nhỏ-vừa hoặc có bottleneck khi tránh xung đột giúp tiết kiệm nhiều bước.

Nhược điểm:

- C6 tụt rất mạnh: chỉ `772.21`, giao `75/100`, đúng hạn `29`.
- Việc tiết kiệm move cost không bù được reward mất do giao trễ/bỏ lỡ.
- Implementation hiện tại là priority-based CBS lite, chưa phải full CBS nhiều bước với constraint tree.
- Thứ tự ưu tiên shipper có thể làm một số shipper bị chờ quá lâu trên bản đồ lớn.
- Tránh collision quá bảo thủ có thể khiến shipper đứng yên thay vì chấp nhận đường vòng có lợi.

Hướng cài đặt cụ thể:

1. Kế thừa `Solver`.
2. Tầng 1, task assignment:
   - tương tự VRP, tính score shipper-order cho các order visible;
   - chọn assignment không trùng shipper/order;
   - cập nhật delivery target cho shipper đang có bag.
3. Tầng 2, conflict resolution:
   - tính độ khẩn cấp của shipper bằng deadline slack và priority;
   - sort shipper theo urgency giảm dần;
   - với mỗi shipper, lấy target hiện tại: delivery ngay, delivery gấp, pickup, delivery thường;
   - lấy move BFS kế tiếp tới target;
   - nếu ô kế tiếp đã reserved, thử move thay thế có khoảng cách còn lại nhỏ nhất;
   - nếu không có move thay thế tốt, đứng yên;
   - kiểm tra edge-swap để tránh hai shipper đổi chỗ nhau.
4. Action vẫn chỉ thực hiện một bước, sau đó re-plan.

Nếu muốn nâng lên CBS đầy đủ:

1. Với mỗi shipper, lập path nhiều bước tới target bằng BFS/A* theo thời gian.
2. Phát hiện vertex conflict `(cell, time)` và edge conflict `(u, v, time)`.
3. Dùng constraint tree:
   - node chứa tập constraint;
   - mỗi lần có conflict, tách thành hai node, mỗi node cấm một agent đi vào conflict đó;
   - re-plan path cho agent bị constraint.
4. Chọn node có tổng path cost thấp nhất.
5. Vì bài toán online, chỉ thực thi bước đầu tiên của path rồi re-plan ở timestep tiếp theo.
6. Cần giới hạn horizon, ví dụ 8-20 bước, để không quá chậm.

## 5. Kết luận và khuyến nghị

Nếu chỉ chọn một thuật toán hiện tại để nộp/chạy Phase 1, nên ưu tiên `ACOSolver` vì tổng điểm cao nhất và giao nhiều đơn nhất. Nếu mục tiêu là ổn định deadline, `VRPOrToolsSolver` đáng chọn hơn vì có số đơn đúng hạn cao nhất và thắng rõ trên C6.

`MAPDCBSSolver` có tiềm năng vì thắng 4/6 config, nhưng cần sửa chiến lược trên bản đồ lớn trước khi dùng làm solver chính. Vấn đề lớn nhất là conflict handling đang quá ngắn hạn và quá bảo thủ, khiến C6 mất nhiều reward.

Hướng phát triển thực dụng tiếp theo:

1. Lấy `VRPOrToolsSolver` làm baseline chính vì ổn định nhất trên config lớn.
2. Mượn exploration có kiểm soát từ `ACOSolver` cho các thời điểm nhiều đơn visible.
3. Chỉ dùng reservation/edge-swap của `MAPDCBSSolver` như module tránh va chạm, không dùng toàn bộ priority policy hiện tại.
4. Thêm ràng buộc deadline của đơn trong bag vào mọi score pickup để tránh nhận thêm đơn làm trễ đơn đang chở.
5. Benchmark lại trên `val_config.txt` sau khi chỉnh, vì `test_config.txt` Phase 1 còn khá nhỏ.
