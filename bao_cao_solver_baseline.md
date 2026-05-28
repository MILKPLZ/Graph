# Báo cáo baseline cho 4 hướng solver

## 1. Mục tiêu

Tạo `solver_baseline/` chứa phiên bản cơ bản nhất của 4 thuật toán đang có trong `solvers/`:

- `BaselineGreedyBFS`: greedy cục bộ + BFS.
- `BaselineVRPOrToolsSolver`: batch assignment kiểu VRP, nhưng chỉ dùng greedy matching một lượt.
- `BaselineACOSolver`: ACO tối giản với pheromone trên cặp `(shipper, order)`.
- `BaselineMAPDCBSSolver`: MAPD-CBS tối giản gồm task assignment + reservation một bước.

Các baseline này dùng để làm mốc phát triển trong báo cáo: từ bản chạy được, quan sát điểm yếu, sau đó giải thích vì sao cần các cải tiến trong solver final.

## 2. Cách chạy

```bash
python -m solver_baseline.run_baselines --config test_config.txt --out results_solver_baseline
```

Kết quả đã lưu tại:

- `results_solver_baseline/summary.json`
- `results_solver_baseline/all_results.json`
- `results_solver_baseline/result_C*.json`

## 3. Thiết kế baseline

### Greedy BFS baseline

Ý tưởng:

- Mỗi shipper tự quyết định theo thông tin hiện tại.
- Nếu đang ở điểm giao thì giao ngay.
- Nếu đang ở điểm lấy thì lấy ngay.
- Nếu có đơn trong túi sắp trễ hoặc túi đầy thì đi giao.
- Ngược lại chọn đơn visible tốt nhất theo reward ước lượng, priority, deadline và khoảng cách BFS.

Tradeoff:

- Ưu điểm: đơn giản, rất nhanh, dễ debug.
- Nhược điểm: không có phối hợp toàn cục nên nhiều shipper có thể cùng đuổi theo vùng đơn giống nhau; không học hotspot; không xử lý collision tốt.

### VRP baseline

Ý tưởng:

- Mỗi timestep tạo một danh sách score cho mọi cặp `(shipper, order)`.
- Score xấp xỉ bằng reward ước lượng chia cho độ dài đường `shipper -> pickup -> delivery`.
- Greedy matching chọn mỗi shipper nhiều nhất một order và mỗi order nhiều nhất một shipper.

Tradeoff:

- Ưu điểm: có phối hợp toàn cục sơ bộ, giảm trùng mục tiêu giữa shipper.
- Nhược điểm: chưa tối ưu route nhiều điểm, chưa xét detour khi shipper đang mang hàng, chưa dùng OR-Tools thật cho bài toán tuyến.

### ACO baseline

Ý tưởng:

- Mỗi ant sinh một assignment shipper-order bằng xác suất phụ thuộc pheromone và heuristic reward/distance.
- Chọn assignment tốt nhất trong vài ant.
- Bay hơi pheromone và deposit nhẹ cho assignment tốt.

Tradeoff:

- Ưu điểm: có khám phá ngẫu nhiên nên đôi khi tốt hơn greedy matching cứng.
- Nhược điểm: số ant ít, không có candidate pruning tốt, pheromone chưa ổn định trên môi trường online thay đổi liên tục.

### MAPD-CBS baseline

Ý tưởng:

- Layer 1: gán task theo nearest feasible order.
- Layer 2: shipper có delivery khẩn cấp được ưu tiên giữ ô kế tiếp.
- Nếu ô kế tiếp đã reserved thì thử bước thay thế tốt hơn, nếu không có thì đứng yên.

Tradeoff:

- Ưu điểm: bắt đầu mô hình hóa xung đột giữa nhiều shipper.
- Nhược điểm: chưa có CBS tree search, chưa kiểm tra edge-swap đầy đủ, reservation chỉ một bước nên dễ bảo thủ hoặc đứng yên nhiều.

## 4. Kết quả baseline trên `test_config.txt`

| Thuật toán | Tổng điểm | Giao/Tổng | Đúng hạn | Runtime tổng xấp xỉ |
|---|---:|---:|---:|---:|
| BaselineACOSolver | 4023.73 | 226/320 | 188 | 2.21s |
| BaselineVRPOrToolsSolver | 3592.41 | 209/320 | 160 | 2.21s |
| BaselineMAPDCBSSolver | 1263.66 | 77/320 | 59 | 1.51s |
| BaselineGreedyBFS | 1203.59 | 82/320 | 55 | 1.60s |

Chi tiết theo config:

| Config | Greedy BFS | VRP baseline | ACO baseline | MAPD-CBS baseline |
|---|---:|---:|---:|---:|
| C1 | 128.80 | 266.56 | 266.56 | 128.11 |
| C2 | 107.44 | 418.85 | 458.51 | 60.13 |
| C3 | 155.20 | 401.93 | 558.93 | 194.44 |
| C4 | 443.80 | 681.12 | 966.38 | 725.68 |
| C5 | 226.65 | 1301.89 | 1224.67 | 104.03 |
| C6 | 141.70 | 522.06 | 548.68 | 51.28 |

Nhận xét:

- `BaselineACOSolver` cao nhất trong nhóm baseline vì stochastic assignment giúp thoát khỏi một số lựa chọn greedy kém.
- `BaselineVRPOrToolsSolver` đứng thứ hai và rất mạnh ở C5, do batch matching giảm trùng mục tiêu.
- `BaselineGreedyBFS` thấp vì thiếu phối hợp toàn cục.
- `BaselineMAPDCBSSolver` chưa tốt dù có tránh xung đột, vì reservation một bước làm solver bảo thủ trong khi task assignment vẫn yếu.

## 5. So sánh với solver hiện tại

Điểm solver hiện tại lấy từ `results/summary.json`.

| Hướng thuật toán | Baseline | Solver hiện tại | Cải thiện |
|---|---:|---:|---:|
| GreedyBFS | 1203.59 | 4962.37 | +3758.79 |
| VRPOrToolsSolver | 3592.41 | 5220.90 | +1628.49 |
| ACOSolver | 4023.73 | 5242.26 | +1218.54 |
| MAPDCBSSolver | 1263.66 | 4597.89 | +3334.23 |

Tổng 4 hướng:

- Baseline: `10083.39`
- Solver hiện tại: `20023.43`
- Chênh lệch: `+9940.04`

## 6. Hướng phát triển từ baseline lên final

### Từ Greedy BFS

Baseline cho thấy local greedy đủ nhanh nhưng không đủ thông minh. Cải tiến hợp lý:

- thêm scoring reward-aware chính xác hơn;
- thêm urgency threshold để quyết định khi nào phải giao;
- thêm reservation đơn giản để giảm nhiều shipper cùng chọn một order;
- thêm smart wander/hotspot khi không có mục tiêu tốt.

Đây là hướng cải thiện có hiệu quả lớn nhất về điểm tuyệt đối trong kết quả hiện tại.

### Từ VRP

Baseline VRP đã tốt hơn Greedy vì có batch assignment. Điểm yếu còn lại là assignment chỉ chọn một pickup, không tối ưu route thật.

Cải tiến hợp lý:

- dùng score matrix tốt hơn thay vì reward/distance thô;
- xét đơn đang nằm gần delivery path như một detour có lợi;
- re-plan rolling horizon mỗi step;
- thêm fallback delivery và collision handling.

Tradeoff chính là runtime và độ phức tạp. Trên `test_config`, hướng VRP hiện tại có điểm cao và ổn định.

### Từ ACO

Baseline ACO đã cạnh tranh tốt nhờ exploration. Tuy nhiên bản cơ bản dễ nhiễu vì môi trường online thay đổi liên tục.

Cải tiến hợp lý:

- giới hạn candidate tốt để giảm nhiễu;
- điều chỉnh số ant/iteration theo kích thước bài toán;
- bay hơi pheromone có kiểm soát;
- kết hợp greedy baseline để không phụ thuộc hoàn toàn vào sampling.

Kết quả hiện tại cho thấy ACO là solver điểm cao nhất trên `test_config`, nhưng cần kiểm soát runtime và overfit.

### Từ MAPD-CBS

Baseline CBS yếu vì chỉ reservation một bước và task assignment đơn giản. Điểm mạnh của hướng này không nằm ở chọn đơn, mà ở xử lý xung đột nhiều agent.

Cải tiến hợp lý:

- priority ordering theo urgency và deadline;
- kiểm tra edge-swap;
- chọn alternative move theo độ lệch đường đi;
- kết hợp global scoring assignment để CBS không chỉ giải quyết collision cho các mục tiêu kém.

Tradeoff là CBS dễ tốn công xử lý xung đột nhưng chưa chắc tăng reward nếu assignment nền yếu.

## 7. Kết luận

Baseline đúng vai trò: chạy được, đơn giản, và bộc lộ rõ điểm yếu từng hướng. Nếu viết báo cáo phát triển thuật toán, nên trình bày theo mạch:

1. Greedy BFS làm mốc local policy.
2. VRP cải thiện bằng global assignment.
3. ACO thêm exploration trên assignment.
4. MAPD-CBS xử lý vấn đề multi-agent conflict.
5. Final solver chọn kết hợp scoring, assignment, urgency và conflict avoidance thay vì chỉ dựa vào một kỹ thuật đơn lẻ.

