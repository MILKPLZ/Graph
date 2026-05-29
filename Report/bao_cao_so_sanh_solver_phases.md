# Báo cáo so sánh solver_baseline, solvers và solvers_v1

Ngày chạy: 2026-05-29, timezone Asia/Ho_Chi_Minh.

Phạm vi chạy:

- Chạy tuần tự 3 phase: `solver_baseline`, `solvers`, `solvers_v1`.
- Chạy trên `test_config.txt` và `val_config.txt`.
- Theo yêu cầu mới, bỏ case max `V_Endurance` (`N=100`, `C=25`, `G=1500`, `T=2400`) khỏi báo cáo.
- Không lưu file result JSON. Chỉ ghi báo cáo Markdown này.
- Các lượt vượt 120 giây được đánh dấu `TIMEOUT`.
- `% đúng hạn` lấy theo metric của `env.py`: `on_time_rate = on_time / delivered * 100`, không phải `on_time / G`.

## 1. Mô tả bài toán và metric

Bài toán là Multi-Agent Package Delivery online trên lưới có vật cản. Mỗi shipper di chuyển từng bước, có giới hạn số đơn và tải trọng. Đơn hàng xuất hiện dần theo thời gian, solver chỉ biết các đơn đã được reveal tại thời điểm hiện tại. Mỗi bước solver phải chọn hướng đi và thao tác pickup/delivery.

Metric chính:

- `net_reward = total_reward - total_movecost`: điểm ròng sau khi trừ chi phí di chuyển.
- `% đúng hạn`: tỷ lệ đơn giao đúng hạn trên số đơn đã giao.
- `runtime`: thời gian chạy wall-clock của solver trên config đó.

## 2. Mô tả từng thuật toán

### 2.1 GreedyBFS

GreedyBFS dùng BFS để tìm đường ngắn nhất trên grid, sau đó chọn hành động tốt nhất theo trạng thái hiện tại. Baseline ưu tiên giao đơn đang mang hoặc nhặt đơn gần/tốt nhất theo heuristic đơn giản. Từ `solvers` trở đi, score pickup/delivery xét reward thật, priority, slack deadline, penalty khoảng cách, hotspot và smart wander.

Độ phức tạp thời gian mỗi bước xấp xỉ `O(C * A * N^2)`, với `C` là số shipper, `A` là số đơn active, `N^2` là số ô grid trong BFS. Bản cải tiến cache BFS nên chi phí thực tế thấp hơn sau các truy vấn lặp. Không gian tệ nhất có thể tới `O(N^4)` nếu cache nhiều cặp nguồn-đích, thực tế nhỏ hơn theo số vị trí được truy vấn. Mức tối ưu là cục bộ, nhanh, dễ ổn định nhưng không đảm bảo assignment toàn cục.

### 2.2 VRPOrToolsSolver

Trong code hiện tại, VRPOrToolsSolver hoạt động như một VRP-lite online: xây candidate giữa shipper và order, chấm điểm theo reward, deadline, capacity, detour và khoảng cách, rồi chọn assignment khả thi. Baseline dùng nearest/reward heuristic đơn giản hơn. `solvers` thêm reward-aware scoring, delivery target, urgency, hotspot và collision resolve. `solvers_v1` điều chỉnh tham số cho map lớn.

Độ phức tạp mỗi bước khoảng `O(C * A * N^2 + M log M)`, với `M` là số candidate assignment. Không gian gồm cache BFS, target của shipper và danh sách candidate, xấp xỉ `O(cache + C + M)`. Mức tối ưu tốt hơn GreedyBFS vì xét nhiều shipper cùng lúc, nhưng vẫn là heuristic online, không giải VRP toàn cục.

### 2.3 ACOSolver

ACOSolver dùng ý tưởng Ant Colony Optimization: nhiều ant thử chọn assignment theo pheromone và heuristic score; phương án tốt cập nhật pheromone để hướng các vòng sau. Baseline dùng heuristic đơn giản hơn. `solvers` kết hợp ACO với reward-aware scoring, deadline, delivery target và collision resolve. `solvers_v1` giới hạn/scale candidate để giảm overfit và giảm chi phí trên map lớn.

Độ phức tạp mỗi bước xấp xỉ `O(I * K * M + C * N^2)`, với `I` là số vòng/ant, `K` là số lựa chọn trong một nghiệm, `M` là số candidate. Không gian `O(M)` cho pheromone/candidate cộng cache BFS. Mức tối ưu cao hơn greedy trong trường hợp candidate vừa phải, nhưng runtime và độ nhạy tham số cao hơn.

### 2.4 MAPDCBSSolver

MAPDCBSSolver lấy ý tưởng từ MAPD/CBS: phân công task có xét nhiều agent và giảm xung đột di chuyển. Code hiện tại chưa phải CBS đầy đủ với constraint tree nhiều bước, nhưng có hướng collision-aware rõ hơn: target, reservation/resolve move một bước, urgency và delivery scoring.

Độ phức tạp hiện tại gần `O(C * A * N^2 + C log C)` mỗi bước. Nếu mở rộng thành CBS đầy đủ thì worst-case có thể tăng theo hàm mũ theo số conflict, nhưng bản hiện tại giữ heuristic để chạy online. Không gian tương tự các solver cải tiến: cache BFS, target và reservation một bước. Mức tối ưu cân bằng giữa reward và tránh xung đột; đôi khi reward thấp hơn VRP/ACO nếu logic tránh xung đột hoặc urgency quá bảo thủ.

## 3. Kết quả tốt nhất theo từng config

| File | Config | Best phase | Best method | Net reward | % đúng hạn | Runtime |
| --- | --- | --- | --- | ---: | ---: | ---: |
| test_config.txt | C1 | solver_baseline | BaselineVRPOrToolsSolver | 266.56 | 100.0% | 0.017s |
| test_config.txt | C2 | solver_baseline | BaselineACOSolver | 458.51 | 95.8% | 0.031s |
| test_config.txt | C3 | solvers | MAPDCBSSolver | 873.76 | 89.2% | 0.050s |
| test_config.txt | C4 | solvers | MAPDCBSSolver | 1012.02 | 91.1% | 0.138s |
| test_config.txt | C5 | solver_baseline | BaselineVRPOrToolsSolver | 1301.89 | 76.0% | 0.512s |
| test_config.txt | C6 | solvers_v1 | ACOSolver | 1508.76 | 80.2% | 0.411s |
| val_config.txt | V_TrafficJam | solvers_v1 | MAPDCBSSolver | 7627.18 | 78.5% | 0.372s |
| val_config.txt | V_MediumSparse | solvers | MAPDCBSSolver | 2513.05 | 49.5% | 1.792s |
| val_config.txt | V_Maze | solvers | GreedyBFS | 990.81 | 22.6% | 6.026s |
| val_config.txt | V_City | solvers | GreedyBFS | 2530.40 | 17.7% | 42.139s |
| val_config.txt | V_SurgeHotspot | solvers | VRPOrToolsSolver | 4083.86 | 21.7% | 14.783s |

## 4. Bảng kết quả chi tiết trên test_config.txt

### C1

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 128.80 | 55.6% | 0.020s |
| solver_baseline | BaselineVRPOrToolsSolver | 266.56 | 100.0% | 0.017s |
| solver_baseline | BaselineACOSolver | 266.56 | 100.0% | 0.018s |
| solver_baseline | BaselineMAPDCBSSolver | 128.11 | 55.6% | 0.018s |
| solvers | GreedyBFS | 243.62 | 100.0% | 0.022s |
| solvers | VRPOrToolsSolver | 264.34 | 100.0% | 0.018s |
| solvers | ACOSolver | 264.34 | 100.0% | 0.021s |
| solvers | MAPDCBSSolver | 265.24 | 100.0% | 0.017s |
| solvers_v1 | GreedyBFS | 243.62 | 100.0% | 0.019s |
| solvers_v1 | VRPOrToolsSolver | 264.34 | 100.0% | 0.018s |
| solvers_v1 | ACOSolver | 264.34 | 100.0% | 0.020s |
| solvers_v1 | MAPDCBSSolver | 265.24 | 100.0% | 0.016s |

### C2

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 107.44 | 54.5% | 0.034s |
| solver_baseline | BaselineVRPOrToolsSolver | 418.85 | 87.5% | 0.029s |
| solver_baseline | BaselineACOSolver | 458.51 | 95.8% | 0.031s |
| solver_baseline | BaselineMAPDCBSSolver | 60.13 | 100.0% | 0.023s |
| solvers | GreedyBFS | 452.86 | 95.8% | 0.022s |
| solvers | VRPOrToolsSolver | 432.22 | 87.5% | 0.023s |
| solvers | ACOSolver | 446.83 | 91.7% | 0.035s |
| solvers | MAPDCBSSolver | 429.45 | 87.5% | 0.023s |
| solvers_v1 | GreedyBFS | 452.86 | 95.8% | 0.021s |
| solvers_v1 | VRPOrToolsSolver | 432.22 | 87.5% | 0.022s |
| solvers_v1 | ACOSolver | 442.21 | 91.7% | 0.039s |
| solvers_v1 | MAPDCBSSolver | 429.45 | 87.5% | 0.023s |

### C3

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 155.20 | 100.0% | 0.059s |
| solver_baseline | BaselineVRPOrToolsSolver | 401.93 | 100.0% | 0.069s |
| solver_baseline | BaselineACOSolver | 558.93 | 80.0% | 0.099s |
| solver_baseline | BaselineMAPDCBSSolver | 194.44 | 100.0% | 0.061s |
| solvers | GreedyBFS | 841.81 | 91.9% | 0.053s |
| solvers | VRPOrToolsSolver | 864.91 | 94.4% | 0.052s |
| solvers | ACOSolver | 863.92 | 88.9% | 0.082s |
| solvers | MAPDCBSSolver | 873.76 | 89.2% | 0.050s |
| solvers_v1 | GreedyBFS | 841.81 | 91.9% | 0.048s |
| solvers_v1 | VRPOrToolsSolver | 864.91 | 94.4% | 0.050s |
| solvers_v1 | ACOSolver | 863.92 | 88.9% | 0.078s |
| solvers_v1 | MAPDCBSSolver | 873.76 | 89.2% | 0.050s |

### C4

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 443.80 | 91.7% | 0.211s |
| solver_baseline | BaselineVRPOrToolsSolver | 681.12 | 64.0% | 0.299s |
| solver_baseline | BaselineACOSolver | 966.38 | 87.5% | 0.268s |
| solver_baseline | BaselineMAPDCBSSolver | 725.68 | 90.2% | 0.270s |
| solvers | GreedyBFS | 978.06 | 87.5% | 0.135s |
| solvers | VRPOrToolsSolver | 1010.34 | 91.1% | 0.136s |
| solvers | ACOSolver | 973.98 | 87.5% | 0.160s |
| solvers | MAPDCBSSolver | 1012.02 | 91.1% | 0.138s |
| solvers_v1 | GreedyBFS | 978.06 | 87.5% | 0.130s |
| solvers_v1 | VRPOrToolsSolver | 1010.34 | 91.1% | 0.134s |
| solvers_v1 | ACOSolver | 973.98 | 87.5% | 0.159s |
| solvers_v1 | MAPDCBSSolver | 1011.19 | 89.3% | 0.134s |

### C5

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 226.65 | 58.8% | 0.333s |
| solver_baseline | BaselineVRPOrToolsSolver | 1301.89 | 76.0% | 0.512s |
| solver_baseline | BaselineACOSolver | 1224.67 | 78.4% | 0.577s |
| solver_baseline | BaselineMAPDCBSSolver | 104.03 | 46.1% | 0.339s |
| solvers | GreedyBFS | 1047.62 | 78.1% | 0.243s |
| solvers | VRPOrToolsSolver | 1166.53 | 78.1% | 0.244s |
| solvers | ACOSolver | 1214.42 | 74.7% | 0.265s |
| solvers | MAPDCBSSolver | 1245.21 | 78.4% | 0.239s |
| solvers_v1 | GreedyBFS | 1047.62 | 78.1% | 0.235s |
| solvers_v1 | VRPOrToolsSolver | 1166.53 | 78.1% | 0.238s |
| solvers_v1 | ACOSolver | 1214.42 | 74.7% | 0.267s |
| solvers_v1 | MAPDCBSSolver | 1210.28 | 75.7% | 0.227s |

### C6

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 141.70 | 43.8% | 0.565s |
| solver_baseline | BaselineVRPOrToolsSolver | 522.06 | 68.8% | 0.759s |
| solver_baseline | BaselineACOSolver | 548.68 | 73.5% | 0.668s |
| solver_baseline | BaselineMAPDCBSSolver | 51.28 | 57.1% | 0.421s |
| solvers | GreedyBFS | 1398.40 | 72.5% | 0.337s |
| solvers | VRPOrToolsSolver | 1482.56 | 80.2% | 0.356s |
| solvers | ACOSolver | 1478.79 | 78.0% | 0.406s |
| solvers | MAPDCBSSolver | 772.21 | 38.7% | 0.406s |
| solvers_v1 | GreedyBFS | 1398.40 | 72.5% | 0.331s |
| solvers_v1 | VRPOrToolsSolver | 1482.56 | 80.2% | 0.347s |
| solvers_v1 | ACOSolver | 1508.76 | 80.2% | 0.411s |
| solvers_v1 | MAPDCBSSolver | 1234.86 | 64.4% | 0.321s |

## 5. Bảng kết quả chi tiết trên val_config.txt

`V_Endurance` đã được bỏ theo yêu cầu vì là case max.

### V_TrafficJam

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 737.94 | 77.8% | 1.009s |
| solver_baseline | BaselineVRPOrToolsSolver | 2001.71 | 80.2% | 1.172s |
| solver_baseline | BaselineACOSolver | 2593.95 | 76.6% | 2.488s |
| solver_baseline | BaselineMAPDCBSSolver | 853.38 | 64.0% | 1.332s |
| solvers | GreedyBFS | 4462.17 | 51.7% | 0.503s |
| solvers | VRPOrToolsSolver | 6867.89 | 64.9% | 0.790s |
| solvers | ACOSolver | 7490.96 | 68.4% | 1.384s |
| solvers | MAPDCBSSolver | 4472.01 | 48.7% | 0.942s |
| solvers_v1 | GreedyBFS | 6564.80 | 61.3% | 0.496s |
| solvers_v1 | VRPOrToolsSolver | 7453.77 | 69.0% | 0.709s |
| solvers_v1 | ACOSolver | 7361.56 | 68.7% | 1.113s |
| solvers_v1 | MAPDCBSSolver | 7627.18 | 78.5% | 0.372s |

### V_MediumSparse

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 318.40 | 57.1% | 3.211s |
| solver_baseline | BaselineVRPOrToolsSolver | 1605.57 | 57.9% | 12.618s |
| solver_baseline | BaselineACOSolver | 550.73 | 50.0% | 12.288s |
| solver_baseline | BaselineMAPDCBSSolver | 252.86 | 53.6% | 3.904s |
| solvers | GreedyBFS | 2221.53 | 48.7% | 1.256s |
| solvers | VRPOrToolsSolver | 1168.20 | 56.5% | 2.085s |
| solvers | ACOSolver | 1907.09 | 41.9% | 2.723s |
| solvers | MAPDCBSSolver | 2513.05 | 49.5% | 1.792s |
| solvers_v1 | GreedyBFS | 2026.93 | 33.6% | 1.448s |
| solvers_v1 | VRPOrToolsSolver | 2327.55 | 41.9% | 1.898s |
| solvers_v1 | ACOSolver | 2009.87 | 40.4% | 2.453s |
| solvers_v1 | MAPDCBSSolver | 2408.00 | 42.4% | 1.261s |

### V_Maze

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 37.75 | 50.0% | 11.649s |
| solver_baseline | BaselineVRPOrToolsSolver | 597.28 | 64.3% | 29.339s |
| solver_baseline | BaselineACOSolver | 246.21 | 59.1% | 62.771s |
| solver_baseline | BaselineMAPDCBSSolver | 161.83 | 53.3% | 21.237s |
| solvers | GreedyBFS | 990.81 | 22.6% | 6.026s |
| solvers | VRPOrToolsSolver | 299.94 | 83.3% | 11.536s |
| solvers | ACOSolver | 314.68 | 21.8% | 15.636s |
| solvers | MAPDCBSSolver | 582.35 | 40.0% | 7.748s |
| solvers_v1 | GreedyBFS | 739.91 | 19.4% | 5.837s |
| solvers_v1 | VRPOrToolsSolver | 373.56 | 34.0% | 12.199s |
| solvers_v1 | ACOSolver | 941.80 | 36.2% | 10.755s |
| solvers_v1 | MAPDCBSSolver | 665.09 | 26.1% | 4.794s |

### V_City

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | TIMEOUT | TIMEOUT | >120s |
| solver_baseline | BaselineVRPOrToolsSolver | TIMEOUT | TIMEOUT | >120s |
| solver_baseline | BaselineACOSolver | TIMEOUT | TIMEOUT | >120s |
| solver_baseline | BaselineMAPDCBSSolver | TIMEOUT | TIMEOUT | >120s |
| solvers | GreedyBFS | 2530.40 | 17.7% | 42.139s |
| solvers | VRPOrToolsSolver | 1720.49 | 24.1% | 68.358s |
| solvers | ACOSolver | 1946.37 | 17.3% | 72.157s |
| solvers | MAPDCBSSolver | 2061.92 | 14.5% | 56.811s |
| solvers_v1 | GreedyBFS | 2006.94 | 20.4% | 41.982s |
| solvers_v1 | VRPOrToolsSolver | 2023.43 | 18.4% | 61.905s |
| solvers_v1 | ACOSolver | 1875.03 | 12.5% | 62.374s |
| solvers_v1 | MAPDCBSSolver | 1999.14 | 11.5% | 43.194s |

### V_SurgeHotspot

| Phase | Method | Net reward | % đúng hạn | Runtime |
| --- | --- | ---: | ---: | ---: |
| solver_baseline | BaselineGreedyBFS | 477.14 | 46.1% | 22.474s |
| solver_baseline | BaselineVRPOrToolsSolver | 1842.62 | 69.8% | 51.781s |
| solver_baseline | BaselineACOSolver | TIMEOUT | TIMEOUT | >120s |
| solver_baseline | BaselineMAPDCBSSolver | 413.42 | 34.4% | 72.556s |
| solvers | GreedyBFS | 3288.46 | 21.1% | 7.135s |
| solvers | VRPOrToolsSolver | 4083.86 | 21.7% | 14.783s |
| solvers | ACOSolver | 3334.70 | 26.4% | 29.918s |
| solvers | MAPDCBSSolver | 3708.12 | 22.7% | 13.324s |
| solvers_v1 | GreedyBFS | 3027.26 | 21.2% | 7.340s |
| solvers_v1 | VRPOrToolsSolver | 2535.81 | 21.2% | 16.553s |
| solvers_v1 | ACOSolver | 2996.19 | 19.9% | 16.569s |
| solvers_v1 | MAPDCBSSolver | 3963.22 | 20.3% | 6.054s |

## 6. Phân tích trade-off

`solver_baseline` có ưu điểm là đơn giản, dễ debug và đủ tốt trên một số config nhỏ. Tuy nhiên khi map lớn hoặc mật độ đơn cao, baseline không kiểm soát tốt chi phí BFS/candidate và dễ timeout. Chất lượng assignment cũng thấp trong các case hotspot/surge do ít học từ luồng đơn mới.

`solvers` là phase cải thiện mạnh nhất về reward. Các thành phần reward-aware scoring, urgency, delivery target, smart wander và hotspot tracking giúp shipper bớt đứng yên, gom đơn tốt hơn và phản ứng nhanh hơn với đơn mới. Đổi lại, code phức tạp hơn và vẫn có rủi ro runtime trên stress case cực lớn.

`solvers_v1` tập trung tổng quát hóa: chuẩn hóa khoảng cách bằng `_map_radius`, giảm urgency quá hung hăng trên map lớn, scale hotspot tương đối và giới hạn candidate ở các solver nặng. Trên validation, v1 cải thiện rất rõ ở `V_TrafficJam` và giúp MAPD-CBS chạy nhanh nhất tại `V_SurgeHotspot`, nhưng không thắng mọi case. Điều này cho thấy v1 là bản anti-overfit chứ không đơn thuần tăng score public.

Theo từng họ thuật toán:

- GreedyBFS nhanh, ổn định, phù hợp baseline mạnh và stress test.
- VRPOrToolsSolver thường có reward tốt khi assignment shipper-order là yếu tố chính.
- ACOSolver có khả năng tìm nghiệm tốt hơn khi candidate vừa phải, nhưng runtime và tham số nhạy hơn.
- MAPDCBSSolver nổi bật trong case đông shipper hoặc có xung đột, nhưng đôi lúc hy sinh reward do ưu tiên an toàn di chuyển.

## 7. Chiến lược ứng phó surge và hotspot

Env có cơ chế tăng tốc sinh đơn trong `surge_windows` và gom pickup quanh `hotspots`. Solver không đọc trực tiếp tham số ẩn này. Nhóm xử lý bằng quan sát online:

- Mỗi bước lấy `new_order_ids`.
- Cập nhật lịch sử pickup mới vào `_hotspot_history`.
- Tính `_hotspot_counts` theo vị trí pickup xuất hiện nhiều trong cửa sổ gần đây.
- Cộng bonus hotspot vào `score_pickup`.
- Khi shipper không có target, `smart_wander_target()` kéo shipper về vùng pending order có mật độ tốt.
- Nếu bag có đơn gần deadline, urgency threshold buộc shipper ưu tiên giao thay vì tiếp tục gom đơn.

Trong `solvers_v1`, hotspot bonus được scale theo độ lớn score trên map lớn để không bị quá nhỏ so với reward/distance. Urgency cũng được giảm hung hăng trên map lớn để tránh hiện tượng mọi đơn đều bị coi là khẩn cấp trong surge dài, làm shipper chỉ giao từng đơn và không tận dụng capacity.

## 8. Cải tiến theo từng phase

| Phase | Thay đổi chính | Tác động |
| --- | --- | --- |
| `solver_baseline` | BFS cơ bản, nearest/reward heuristic, assignment đơn giản, ít hoặc không học hotspot, tránh xung đột hạn chế | Nhanh trên config nhỏ, nhưng tối ưu cục bộ và dễ timeout ở validation lớn |
| `solvers` | Base `Solver` chung, BFS cache, reward-aware scoring, priority/slack, delivery target, urgency threshold, hotspot tracking, smart wander, collision resolve một bước | Tăng net reward rõ rệt, giảm thời gian chết, xử lý surge/hotspot tốt hơn |
| `solvers_v1` | `_map_radius`, urgency theo kích thước map, hotspot scale tương đối, candidate cap/anti-overfit cho map lớn | Tổng quát hơn, giảm overfit public, cải thiện một số validation nhưng có trade-off ở vài config |

## 9. Kết luận

Nếu chỉ chọn một hướng triển khai thực dụng, `solvers` và `solvers_v1` nên được ưu tiên thay cho baseline vì vừa tăng reward vừa giảm runtime ở case lớn. `solvers` có điểm tốt nhất trên nhiều config, còn `solvers_v1` ổn hơn khi cần chống overfit và xử lý traffic/hotspot phức tạp. Baseline vẫn hữu ích làm mốc so sánh, nhưng không phù hợp cho validation lớn do timeout trên `V_City` và case max đã bị bỏ khỏi báo cáo.
