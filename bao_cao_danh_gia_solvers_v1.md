# Báo cáo đánh giá `solvers_v1`

## 1. Thay đổi đã thực hiện

Tạo folder `solvers_v1` từ `solvers` hiện tại và thêm runner riêng:

```bash
python3 run_test_solvers_v1.py --config test_config.txt --out results_solvers_v1_test_config --method all
```

Các thay đổi chính theo `plans/01-solver-generalization.md`:

- `solver.py`: thêm `_map_radius` bằng 90th-percentile BFS distance từ tâm hợp lệ.
- `solver.py`: đổi distance penalty trong `score_pickup()` từ mẫu số `N` sang `_map_radius`.
- `mapd_cbs_solver.py`: scale urgency theo `T`.
- `mapd_cbs_solver.py`: tăng detour tolerance thành `max(2, N // 8)`.
- `vrp_ortools.py`: bật detour threshold/proportional bonus có điều kiện cho map lớn hoặc mật độ shipper cao.
- `greedy_bfs.py`: reservation threshold dùng `_map_radius` thay vì `N`.
- `aco_solver.py`: giới hạn candidate size và đổi seed theo config khi map lớn/dense.
- `solver.py`: hotspot bonus scale theo score khi map lớn/dense.

Điều chỉnh so với plan gốc:

- Sửa bug indentation trong `_find_valid_center()`. Bug này có thật trong `solvers_v1`.
- Phase 3 (`urgent_slack_threshold` từ `1.5` xuống `0.5`) chỉ bật khi `N > 20`; bật global làm tụt mạnh C5/C6.
- Phase 4 của VRP được dùng có điều kiện:
  - bật khi `N > 20` hoặc `C > N`;
  - giữ logic cũ trên `test_config` nhỏ để tránh regression.
- Không giữ sticky assignment cho VRP. Benchmark thực tế làm `V_Maze` giảm từ `179/800` xuống `34/800`.

## 2. Kết quả trên `test_config.txt`

Kết quả cuối lưu tại `results_solvers_v1_test_config/summary.json`.

| Thuật toán | Baseline | solvers_v1 | Chênh lệch | Giao/Tổng v1 | Đúng hạn | Trễ | Bỏ lỡ |
|---|---:|---:|---:|---:|---:|---:|---:|
| ACOSolver | 5242.26 | 5242.26 | +0.00 | 295/320 | 243 | 52 | 25 |
| VRPOrToolsSolver | 5220.90 | 5220.90 | +0.00 | 293/320 | 249 | 44 | 27 |
| GreedyBFS | 4962.37 | 4962.37 | +0.00 | 284/320 | 234 | 50 | 36 |
| MAPDCBSSolver | 4597.89 | 4564.26 | -33.63 | 279/320 | 204 | 75 | 41 |

Tổng điểm 4 solver:

- Baseline: `20023.43`
- `solvers_v1`: `19989.80`
- Chênh lệch: `-33.63`

Nhận xét:

- `ACOSolver`, `VRPOrToolsSolver`, `GreedyBFS` giữ nguyên điểm trên `test_config`.
- `MAPDCBSSolver` giảm nhẹ `33.63` điểm do thay đổi CBS; C6 vẫn là điểm yếu lớn.
- Tổng điểm giảm nhẹ, nhưng đổi lại bản v1 sửa bug thật trong `_find_valid_center()` và cải thiện val configs lớn.

## 3. Kết quả generalization của VRP trên val core4

Benchmark có kiểm soát cho `VRPOrToolsSolver` trên 4 config val đã có baseline cũ:

```bash
# chạy 4 config đầu trong val_config.txt:
# V_TrafficJam, V_MediumSparse, V_Maze, V_City
```

Kết quả lưu tại `results_solvers_v1_vrp_val_core4/summary.json`.

| Config | Baseline score | v1 score | Chênh lệch | Baseline giao | v1 giao |
|---|---:|---:|---:|---:|---:|
| V_TrafficJam | 6867.89 | **7453.77** | **+585.88** | 439/500 | 461/500 |
| V_MediumSparse | 1168.20 | **2327.55** | **+1159.35** | 92/300 | 198/300 |
| V_Maze | 299.94 | **373.56** | **+73.62** | 18/800 | 47/800 |
| V_City | 1720.49 | **2023.43** | **+302.94** | 294/1000 | 407/1000 |

Tổng VRP trên val core4:

- Baseline: `10056.53`
- `solvers_v1`: `12178.31`
- Chênh lệch: `+2121.78`
- Số đơn giao: `843 -> 1113`

Đây là cải thiện chính của bản v1: giữ được hầu hết điểm Phase 1 nhỏ, đồng thời giảm collapse của VRP trên map lớn. Mức tăng ở `V_Maze` sau khi sửa đúng indentation không còn lớn như bản v1 trước review, nhưng vẫn tốt hơn baseline.

## 4. Kết quả ACO spot-check

Sau khi cap `_candidate_k` và dùng seed theo config cho map lớn/dense:

| Config | Baseline score | v1 score | Baseline giao | v1 giao |
|---|---:|---:|---:|---:|
| V_MediumSparse | 1907.09 | **1986.96** | 186/300 | 196/300 |
| V_Maze | 314.68 | **941.80** | 55/800 | 94/800 |

## 5. Đánh giá tradeoff

Ưu điểm:

- `VRPOrToolsSolver` generalize tốt hơn trên map lớn.
- `ACOSolver` cải thiện rõ ở spot-check `V_Maze`.
- `_find_valid_center()` đã được sửa đúng, tránh map-radius sai trên map center bị chặn.
- Thay đổi được tách riêng trong `solvers_v1`, không ảnh hưởng `solvers` gốc.
- Runner riêng giúp benchmark v1 độc lập.

Nhược điểm:

- `MAPDCBSSolver` chưa được cải thiện ổn định; C6 vẫn thấp và tổng `test_config` giảm nhẹ.
- Sticky assignment cho VRP bị loại bỏ vì làm `V_Maze` kém hơn.
- `V_Endurance` và `V_SurgeHotspot` chưa chạy hết vì runtime lớn và không có baseline cũ tương ứng trong `results_val`.

## 6. Khuyến nghị dùng tiếp

Nếu cần chọn một solver từ bản v1, nên chọn `VRPOrToolsSolver` vì tradeoff tốt nhất:

- `test_config`: giữ nguyên `5220.90`;
- val core4: tăng từ `10056.53` lên `12178.31`;
- cải thiện mạnh nhất ở `V_MediumSparse`, `V_TrafficJam`, `V_City`.

Hướng tiếp theo:

1. Giữ `VRPOrToolsSolver` v1 làm solver chính.
2. Không bật sticky assignment VRP kiểu hiện tại; nếu thử lại cần hysteresis có điều kiện theo score-ratio thay vì giữ cứng.
3. Không bật Phase 3 global cho tất cả solver; hiện chỉ bật `N > 20`.
4. Tách riêng một plan mới cho CBS vì sửa detour/urgency hiện tại chưa đủ để cứu C6.
5. Tối ưu runtime cho `V_Endurance` và `V_SurgeHotspot` trước khi benchmark full val.
