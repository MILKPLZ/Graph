# Shopee Delivery Optimization (Online MAPD)

Dự án này lấy cảm hứng từ hệ thống vận hành thực tế của Shopee, áp dụng các thuật toán đồ thị và heuristic để giải quyết bài toán phân công đơn hàng online theo thời gian thực.

## Tổng quan bài toán

Trong môi trường mô phỏng, hệ thống phải điều phối một đội ngũ shipper di chuyển trên bản đồ lưới (grid map) có vật cản để nhận và giao hàng. Các đơn hàng không được biết trước mà xuất hiện liên tục (online). Mỗi solver phải ra quyết định tối ưu dựa trên:
*   **Ràng buộc shipper:** Sức chứa tối đa (số lượng đơn) và tải trọng tối đa.
*   **Đặc tính đơn hàng:** Vị trí lấy/giao, khối lượng, mức độ ưu tiên (Priority) và hạn chót giao hàng (Deadline).
*   **Mục tiêu:** Tối đa hóa lợi nhuận ròng (Net Reward = Tiền thưởng giao hàng - Chi phí di chuyển - Phạt giao trễ).

## Cấu trúc Repository

Kho lưu trữ được tổ chức thành các thành phần chính sau:

*    **`Report/`**: Chứa mã nguồn LaTeX và bản PDF báo cáo chi tiết của dự án, trình bày cơ sở lý thuyết và phân tích kết quả.
*    **`solvers/`**: Thư mục chứa các **thuật toán đã được tối ưu hóa (Final)** mang lại hiệu suất cao nhất. Bao gồm:
    *   `greedy_bfs.py`: Tham lam cục bộ kết hợp BFS.
    *   `vrp_ortools.py`: Phân công theo lô (Rolling-Horizon VRP).
    *   `aco_solver.py`: Tối ưu hóa đàn kiến (Ant Colony Optimization).
    *   `mapd_cbs_solver.py`: Giải quyết xung đột di chuyển (MAPD-CBS-lite).
*    **`solver_baseline/`**: Thư mục chứa các thuật toán cơ sở (Baselines). Đây là các phiên bản đơn giản, dùng làm mốc đối chiếu (benchmark) để đánh giá mức độ cải thiện của các thuật toán Final.
