# Phân tích bài toán Online MAPD Graph Shopee và 8 file cần dùng để triển khai solver

## 0. Mục tiêu của tài liệu

Tài liệu này tổng hợp lại bài toán, các thay đổi mới của đề, vai trò của từng file được cung cấp, cách `run_test.py` chấm bài, cách `DeliveryEnv` vận hành, và hướng triển khai 4 thuật toán trong thư mục `solvers`:

- `greedy_bfs.py`
- `vrp_ortools.py`
- `aco_solver.py`
- `mapd_cbs_solver.py`

Mục tiêu là sau khi đọc tài liệu này, bạn có thể hiểu rõ:

1. Bài toán đang yêu cầu tối ưu cái gì.
2. Solver được phép nhìn thấy dữ liệu nào tại từng thời điểm.
3. Mỗi action gửi vào môi trường có dạng gì.
4. 8 file đang đóng vai trò gì.
5. Những phần nào hiện đã chạy được, phần nào còn là skeleton.
6. Nên triển khai thuật toán theo thứ tự nào để vừa đúng đề, vừa có điểm thực nghiệm.

---

## 1. Tóm tắt bản chất bài toán

Đây là bài toán **Online Multi-Agent Pickup and Delivery trên bản đồ lưới**.

Có một đội `C` shipper hoạt động đồng thời trên bản đồ `N × N`. Bản đồ gồm:

- `0`: ô trống, đi được.
- `1`: vật cản, không đi được.

Mỗi shipper có:

- vị trí hiện tại;
- tải trọng tối đa `W_max`;
- sức chứa số đơn tối đa `K_max`;
- danh sách đơn đang mang trong `bag`.

Đơn hàng xuất hiện dần theo thời gian, không xuất hiện toàn bộ ngay từ đầu. Mỗi đơn có:

- điểm lấy hàng `(sx, sy)`;
- điểm giao hàng `(ex, ey)`;
- deadline `et`;
- trọng lượng `w`;
- mức ưu tiên `p ∈ {1, 2, 3}`;
- thời điểm xuất hiện `appear_t`.

Mục tiêu cuối cùng là tối đa hóa:

```text
net_reward = tổng reward giao hàng + tổng chi phí di chuyển
```

Trong bản `env.py` mới, `net_reward` được môi trường tính nội bộ và solver nên trả về kết quả bằng `env.result(...)`, không tự tính lại công thức reward/cost.

---

## 2. Các thay đổi quan trọng của đề bản mới

Bản mới thay đổi rất lớn so với phiên bản đầu.

### 2.1. Môi trường chuyển sang online/stateful

Trước đây, `env.py` sinh sẵn toàn bộ orders, solver có thể clone danh sách orders rồi tự mô phỏng.

Bản mới thì khác:

- Chỉ tổng số đơn `G` được biết từ đầu.
- Đơn hàng được sinh/reveal dần theo thời gian.
- Solver chỉ thấy observation hiện tại.
- Solver không được lập kế hoạch dựa trên các đơn chưa xuất hiện.

Vì vậy, solver phải chạy theo kiểu:

```text
obs = env.reset()
while chưa done:
    đọc obs hiện tại
    quyết định action cho từng shipper
    obs, reward, done, info = env.step(actions)
return env.result(method_name, elapsed_sec)
```

### 2.2. Mỗi timestep chỉ được chọn một cargo operation

Tại mỗi bước, mỗi shipper có action dạng:

```text
(move, cargo_op)
```

Trong đó:

- `move ∈ {S, U, D, L, R}`;
- `cargo_op = 0`: không làm gì;
- `cargo_op = 1`: pickup;
- `cargo_op = 2`: delivery.

Tại cùng một timestep, một shipper **không được vừa pickup vừa delivery**.

### 2.3. Pickup chỉ nhặt đúng một đơn

Nếu shipper chọn `cargo_op = 1`, môi trường sẽ nhặt đúng **một đơn tốt nhất** tại ô hiện tại.

Thứ tự ưu tiên khi có nhiều đơn tại cùng ô:

```text
priority cao hơn → deadline sớm hơn → id nhỏ hơn
```

Tức là đơn hỏa tốc được ưu tiên hơn đơn nhanh, đơn nhanh được ưu tiên hơn đơn tiêu chuẩn.

### 2.4. Delivery có thể giao nhiều đơn cùng điểm đích

Nếu shipper chọn `cargo_op = 2`, môi trường sẽ giao tất cả đơn trong `bag` có điểm giao trùng với vị trí hiện tại của shipper.

Ví dụ nếu shipper đang đứng tại `(5, 6)` và đang mang 3 đơn đều có destination `(5, 6)`, thì một action delivery có thể giao cả 3 đơn.

### 2.5. Collision do môi trường xử lý

Solver gửi move mong muốn cho từng shipper. Môi trường xử lý va chạm trong `_apply_moves()`.

Nguyên tắc chính:

- shipper có id nhỏ hơn được xử lý trước;
- nếu ô target đã bị chiếm, shipper đó giữ nguyên vị trí;
- nếu move ra ngoài/vào vật cản, shipper cũng giữ nguyên vị trí.

Solver vẫn nên chủ động tránh xung đột để tăng hiệu quả, nhưng va chạm cơ bản đã được môi trường kiểm soát.

---

## 3. Luồng chạy tổng quát của grader

`run_test.py` là file chấm chính. Luồng chạy của nó là:

```text
1. Load 4 solver class từ thư mục solvers.
2. Load danh sách config từ test_config.txt.
3. Với mỗi config:
      tạo seed ổn định riêng cho config đó;
      với mỗi solver được chọn:
          tạo DeliveryEnv mới;
          khởi tạo solver bằng solver_cls(env);
          gọi solver.run();
          lấy dict kết quả solver trả về;
          cộng net_reward vào bảng tổng kết.
4. Ghi kết quả ra thư mục results/.
```

Điểm cực kỳ quan trọng:

```text
Mỗi solver được chạy trên một env riêng nhưng cùng config/seed.
```

Điều này giúp các solver không làm bẩn state của nhau.

---

## 4. Dạng action solver phải trả cho env.step()

Solver có thể truyền `actions` dưới dạng dict hoặc list.

Khuyến nghị dùng dict:

```text
{
    shipper_id_0: (move_0, op_0),
    shipper_id_1: (move_1, op_1),
    ...
}
```

Ví dụ:

```text
{
    0: ("R", 0),
    1: ("U", 1),
    2: ("S", 2),
}
```

Ý nghĩa:

- shipper 0 đi sang phải, không pickup/delivery;
- shipper 1 đi lên, sau khi di chuyển nếu đứng ở điểm pickup thì nhặt một đơn;
- shipper 2 đứng yên, sau đó giao tất cả đơn trong bag có destination tại vị trí hiện tại.

Nếu solver không gửi action cho một shipper, env hiểu shipper đó đứng yên và không làm gì.

---

## 5. Observation solver nhận được

`env.observe()` trả về một dict gồm các thành phần chính:

```text
t: thời điểm hiện tại
N, C, G, T: thông tin config
grid: bản đồ
orders: các đơn đang visible và chưa delivered
new_order_ids: id các đơn vừa được reveal ở bước gần nhất
shippers: danh sách trạng thái shipper hiện tại
done: đã kết thúc episode chưa
```

Điểm cần nhớ:

```text
obs["orders"] không chứa đơn tương lai.
```

Do đó, VRP/ACO/MAPD-CBS chỉ được tối ưu trên các đơn đang visible tại thời điểm hiện tại.

---

## 6. Phân tích 8 file được cung cấp

Bộ xử lý hiện tại gồm 8 file quan trọng:

1. `env.py`
2. `run_test.py`
3. `test_config.txt`
4. `solvers/solver.py`
5. `solvers/greedy_bfs.py`
6. `solvers/vrp_ortools.py`
7. `solvers/aco_solver.py`
8. `solvers/mapd_cbs_solver.py`

---

# PHẦN A — 3 file môi trường/grader/config

## 7. File `env.py`

`env.py` là file quan trọng nhất về mặt luật chơi. Nó định nghĩa toàn bộ môi trường online.

### 7.1. Vai trò chính

`env.py` chứa:

- hằng số reward/cost;
- dataclass `Order`;
- dataclass `Shipper`;
- hàm kiểm tra ô hợp lệ;
- hàm tính reward giao hàng;
- hàm tính chi phí di chuyển;
- parser action;
- xử lý move/collision;
- sinh đơn online;
- class `DeliveryEnv`.

Sinh viên không sửa file này khi nộp.

### 7.2. Dataclass `Order`

Một order có các trường:

```text
id
sx, sy
ex, ey
et
w
p
appear_t
picked
delivered
carrier
deliver_t
```

Trong observation, solver nhìn thấy các order chưa delivered.

### 7.3. Dataclass `Shipper`

Một shipper có:

```text
id
r, c
W_max
K_max
bag
total_reward
steps_moved
```

Các method quan trọng:

- `position`: trả `(r, c)`.
- `move_to(pos, orders)`: di chuyển và tính move cost.
- `can_carry(order, orders)`: kiểm tra sức chứa và tải trọng.
- `can_pickup(order, orders)`: kiểm tra đứng đúng pickup và còn khả năng chở.
- `pickup_best(orders)`: nhặt đúng một đơn tốt nhất tại ô hiện tại.
- `can_deliver(order)`: kiểm tra có thể giao đơn tại vị trí hiện tại.
- `deliver(order, t, T)`: giao đơn và cộng reward cho shipper.

Solver nên dùng các thuộc tính trong observation, không nên đột biến trực tiếp object thật trong env.

### 7.4. Reward helpers

Các hàm chính:

```text
r_base(w)
delivery_reward(order, t_delivery, T)
move_cost(w_carried, w_max)
```

Không nên tự viết lại công thức reward/cost trong solver nếu không cần thiết. Cứ để env xử lý trong `env.step()`.

### 7.5. `DeliveryEnv.reset()`

Reset episode về ban đầu:

- đặt `t = 0`;
- reset random state;
- xóa orders hiện tại;
- khởi tạo shipper;
- reveal các đơn xuất hiện ở thời điểm đầu;
- trả observation ban đầu.

Solver cần gọi `env.reset()` ở đầu `run()`.

### 7.6. `DeliveryEnv.step(actions)`

Đây là hàm quan trọng nhất.

Thứ tự xử lý:

```text
1. Parse action.
2. Apply moves và xử lý collision.
3. Với từng shipper:
      nếu op == 1: pickup_best()
      nếu op == 2: deliver_many()
4. Cộng reward/cost.
5. Tăng t.
6. Reveal đơn mới nếu chưa hết T.
7. Trả obs mới, reward bước, done, info.
```

Solver chỉ cần quyết định `actions`; env sẽ xử lý luật mô phỏng.

### 7.7. `DeliveryEnv.result(method, elapsed_sec)`

Trả kết quả cuối cùng đúng format grader cần:

```text
method
config_name
total_orders
orders_generated
delivered
on_time
late
missed
delivery_rate
on_time_rate
total_reward
total_movecost
net_reward
elapsed_sec
shipper_rewards
status
```

Solver nên kết thúc bằng:

```text
return env.result(method_name, elapsed_sec)
```

---

## 8. File `run_test.py`

`run_test.py` là grader chính thức. Không sửa file này.

### 8.1. Solver được load cố định

Grader load đúng 4 file/class:

```text
GreedyBFS          từ greedy_bfs.py
VRPOrToolsSolver  từ vrp_ortools.py
ACOSolver         từ aco_solver.py
MAPDCBSSolver     từ mapd_cbs_solver.py
```

Vì vậy không được đổi tên file, không được đổi tên class.

### 8.2. Argument `--method`

Bản mới hỗ trợ:

```text
--method all
```

hoặc chạy một solver cụ thể:

```text
--method GreedyBFS
--method VRPOrToolsSolver
--method ACOSolver
--method MAPDCBSSolver
```

Điều này hữu ích cho Phase 2: nếu một phương pháp tốt nhất, có thể chỉ chạy phương pháp đó để tiết kiệm thời gian.

### 8.3. Mỗi solver có env riêng

Grader gọi:

```text
env = DeliveryEnv(env_cfg, seed=seed)
solver = solver_cls(env)
result = solver.run()
```

Mỗi solver nhận một env mới nên state không bị leak giữa các thuật toán.

### 8.4. Score chính

Grader dùng:

```text
net_reward
```

để cộng tổng điểm theo phương pháp.

Vì vậy solver phải tối đa hóa `net_reward`, không chỉ tối đa hóa số đơn giao.

---

## 9. File `test_config.txt`

`test_config.txt` Phase 1 bản mới có 6 config.

| Config | N | C | G | T | Nhận xét |
|---|---:|---:|---:|---:|---|
| C1 | 7 | 2 | 15 | 240 | nhỏ, bản đồ có tường bao |
| C2 | 10 | 2 | 25 | 240 | nhỏ-vừa, có vật cản |
| C3 | 12 | 3 | 40 | 360 | vừa, có vùng bị chia cắt |
| C4 | 15 | 4 | 60 | 480 | bottleneck rõ hơn |
| C5 | 18 | 5 | 80 | 600 | lớn, nhiều hành lang |
| C6 | 20 | 5 | 100 | 720 | lớn nhất Phase 1 |

Các bản đồ đều có tường bao ngoài bằng `1`. Shipper chỉ xuất phát ở ô trống bên trong.

Surge/hotspot không công bố trong config Phase 1, nhưng env tự sinh ẩn bằng seed ổn định.

---

# PHẦN B — 5 file trong thư mục `solvers`

## 10. File `solvers/solver.py`

Đây là base class hiện tại cho tất cả solver.

### 10.1. Trạng thái hiện tại

`solver.py` mới đã phù hợp với env online:

- nhận `env: DeliveryEnv`;
- lưu `self.env`;
- lưu `self.cfg`;
- lưu `self.grid`;
- không còn gọi `clone_orders()` như bản cũ.

Đây là sửa đổi đúng.

### 10.2. `default_result()`

`default_result()` chỉ dùng cho skeleton chưa cài đặt. Nó trả:

```text
delivered = 0
net_reward = 0
status = TODO
```

Vì vậy, bất kỳ solver nào còn gọi `default_result()` trong `run()` thì solver đó chắc chắn bị 0 điểm.

### 10.3. Nên bổ sung gì vào `solver.py`?

Để triển khai hiệu quả 4 thuật toán, nên đưa các utility dùng chung vào `solver.py`, ví dụ:

- BFS shortest path;
- cache distance;
- next move theo BFS;
- hàm tính score đơn hàng;
- hàm kiểm tra shipper đang đứng ở điểm giao;
- hàm chọn cargo op ưu tiên delivery trước pickup;
- reservation table đơn giản để tránh collision.

Như vậy 4 solver có thể dùng chung logic môi trường, giảm code lặp.

---

## 11. File `solvers/greedy_bfs.py`

Đây là file đã có implementation thật.

### 11.1. Trạng thái hiện tại

Greedy BFS hiện tại đã tương thích với env online.

Luồng chạy:

```text
obs = env.reset()
while not done:
    actions = _decide_actions(obs)
    obs, _, done, _ = env.step(actions)
return env.result(...)
```

Đây là đúng format.

### 11.2. Logic hiện tại

Solver có các thành phần:

- BFS utilities:
  - `_neighbors()`
  - `_bfs_parents()`
  - `_distance()`
  - `_next_move()`
- chọn delivery:
  - chọn đơn trong bag có khoảng cách tới delivery gần nhất;
- chọn pickup:
  - chọn đơn visible chưa pickup mà shipper có thể chở;
  - ưu tiên pickup gần nhất;
- tạo action:
  - nếu đến delivery thì `op = 2`;
  - nếu đến pickup thì `op = 1`;
  - nếu chưa tới thì `op = 0`.

### 11.3. Điểm mạnh

- Đúng API online.
- Dùng env.step, không tự tính reward.
- Có BFS tránh vật cản.
- Có cache distance/next move.
- Không nhìn đơn tương lai.
- Có thể chạy được ngay.

### 11.4. Điểm yếu hiện tại

Greedy hiện tại vẫn còn đơn giản:

- chọn pickup chủ yếu theo khoảng cách;
- chưa tính reward dự kiến;
- chưa tính khả năng đúng hạn;
- chưa tính tổng quãng đường pickup → delivery;
- chưa tối ưu gom nhiều đơn cùng đường;
- chưa phát hiện hotspot;
- chưa chủ động tránh nhiều shipper đi cùng một corridor.

### 11.5. Nên nâng cấp Greedy như thế nào?

Hàm chọn pickup nên dùng score tổng hợp:

```text
score cao nếu:
    priority cao
    reward dự kiến cao
    deadline còn kịp
    distance tới pickup thấp
    distance pickup → delivery thấp
    shipper còn đủ capacity
    đơn nằm trong vùng nhiều đơn mới/hotspot quan sát được

score thấp nếu:
    gần như chắc chắn trễ
    quá xa
    reward thấp
    nặng nhưng shipper tải thấp
```

Hàm chọn delivery nên ưu tiên:

```text
1. Nếu đang đứng tại điểm giao của bất kỳ đơn nào trong bag: op=2 ngay.
2. Nếu có đơn sắp trễ: đi giao đơn đó.
3. Nếu nhiều đơn cùng destination: ưu tiên destination đó.
4. Nếu không, chọn delivery có trade-off tốt nhất giữa deadline và khoảng cách.
```

---

## 12. File `solvers/vrp_ortools.py`

### 12.1. Trạng thái hiện tại

File này hiện vẫn là skeleton:

```text
run() -> default_result(...)
```

Nghĩa là chưa chạy env, chưa có VRP, và chắc chắn `net_reward = 0`.

### 12.2. VRP trong bài này nên hiểu như thế nào?

Bài này là online, không thể giải VRP toàn bộ đơn ngay từ đầu.

Cách đúng là **rolling-horizon VRP**:

```text
Tại thời điểm t:
    lấy các đơn visible hiện tại;
    lấy trạng thái shipper hiện tại;
    xây một bài toán phân công/route ngắn hạn;
    quyết định target tiếp theo cho từng shipper;
    thực hiện 1 bước;
    bước sau re-plan lại.
```

### 12.3. OR-Tools có thể gặp rủi ro

Đề cấm `pip install`, nên nếu Kaggle không có sẵn OR-Tools thì import sẽ lỗi.

Do đó, VRP solver nên có fallback:

```text
Nếu import OR-Tools thành công:
    dùng OR-Tools cho rolling-horizon nhỏ.
Nếu không:
    dùng heuristic VRP-like assignment.
```

Fallback vẫn nên có kết quả > 0 để không bị mất toàn bộ điểm.

### 12.4. Thiết kế VRP-like thực dụng nếu không có OR-Tools

Có thể làm như sau:

```text
Mỗi vài bước hoặc mỗi bước:
    Với mỗi shipper:
        nếu đang có bag:
            chọn điểm giao tốt nhất.
        nếu rảnh hoặc còn capacity:
            xét top K đơn visible theo priority/deadline/reward.
    Tạo ma trận score shipper-order.
    Chọn các cặp shipper-order tốt nhất không trùng order.
    Mỗi shipper đi BFS một bước tới target.
```

Điểm khác Greedy:

- Greedy chọn theo từng shipper tuần tự.
- VRP-like nên chọn theo batch/global matching để tránh nhiều shipper cùng đuổi một đơn.

### 12.5. Mục tiêu triển khai tối thiểu

VRP solver tối thiểu cần:

- chạy được online bằng `env.step()`;
- không gọi `default_result()`;
- có assignment theo batch;
- tránh chọn trùng pickup;
- trả `env.result("VRPOrToolsSolver", elapsed_sec)`.

---

## 13. File `solvers/aco_solver.py`

### 13.1. Trạng thái hiện tại

File này hiện vẫn là skeleton:

```text
run() -> default_result(...)
```

Chưa có pheromone, chưa có heuristic, chưa chạy env.

### 13.2. ACO trong bài này nên hiểu như thế nào?

ACO nên được áp dụng trên **tập đơn visible tại thời điểm hiện tại**, không dùng đơn tương lai.

Vì bài có nhiều timestep, ACO không nên cố tối ưu cả episode. Thay vào đó dùng rolling horizon:

```text
Tại thời điểm t:
    lấy một tập ứng viên gồm các đơn visible tốt nhất;
    mỗi ant xây một route ngắn cho một shipper hoặc cả fleet;
    đánh giá route theo reward dự kiến / deadline / distance;
    chọn action đầu tiên từ route tốt nhất;
    env.step(actions);
    cập nhật pheromone nhẹ;
    lặp lại.
```

### 13.3. Vì sao phải giới hạn ACO?

Config lớn nhất Phase 1 có `N=20`, `C=5`, `G=100`, `T=720`. Nếu mỗi bước chạy nhiều ant và nhiều iteration, sẽ chậm.

Nên giới hạn:

```text
top_orders_per_step khoảng 10-20
num_ants khoảng 8-20
num_iterations khoảng 3-10
chỉ re-plan mỗi vài bước hoặc khi target invalid
```

### 13.4. Heuristic nên dùng

Xác suất chọn order nên tăng khi:

- priority cao;
- reward dự kiến cao;
- deadline gần nhưng vẫn kịp;
- khoảng cách phục vụ ngắn;
- shipper có đủ capacity.

Một heuristic ý tưởng:

```text
eta(order, shipper) tăng theo:
    priority_weight × estimated_reward
    / (1 + distance_to_pickup + distance_pickup_to_delivery)
```

Và giảm mạnh nếu đơn gần như không thể giao đúng hạn.

### 13.5. Mục tiêu triển khai tối thiểu

ACO solver tối thiểu cần:

- chạy online;
- không gọi `default_result()`;
- có lựa chọn order dựa trên pheromone + heuristic;
- có random seed ổn định;
- giới hạn runtime;
- trả `env.result("ACOSolver", elapsed_sec)`.

---

## 14. File `solvers/mapd_cbs_solver.py`

### 14.1. Trạng thái hiện tại

File này hiện vẫn là skeleton:

```text
run() -> default_result(...)
```

Chưa có MAPD, chưa có CBS, chưa chạy env.

### 14.2. MAPD-CBS trong bài này nên hiểu như thế nào?

MAPD-CBS gồm hai phần:

1. **Task assignment**: shipper nào đi lấy/giao đơn nào.
2. **Path planning tránh xung đột**: các shipper đi như thế nào để không tranh chấp ô/cạnh.

CBS chuẩn có thể khá phức tạp. Với bài này, hướng thực dụng là:

```text
Task assignment: dùng Greedy/score để chọn target.
Path planning: dùng reservation table hoặc CBS-lite để tránh conflict trong horizon ngắn.
```

### 14.3. Vì sao cần tránh conflict?

Bản đồ mới có nhiều bottleneck, cổng hẹp, tường bao. Nếu nhiều shipper cùng đi vào một corridor hẹp, env sẽ cho shipper id nhỏ đi trước, shipper sau có thể bị đứng yên nhiều bước.

Điều này làm giảm reward vì:

- trễ deadline;
- mất cơ hội pickup;
- shipper bị idle ngoài ý muốn.

### 14.4. CBS-lite/reservation table thực dụng

Một bản triển khai vừa đủ có thể làm:

```text
Mỗi bước:
    Với mỗi shipper, chọn target như Greedy nâng cấp.
    Tính đường BFS ngắn tới target.
    Xét shipper theo id hoặc theo độ khẩn cấp.
    Reserve ô kế tiếp cho shipper đã chọn trước.
    Nếu ô kế tiếp bị reserve:
        thử move thay thế.
        nếu không có, đứng yên.
    Tránh edge swap nếu có thể.
```

Đây chưa phải CBS đầy đủ, nhưng có thể trình bày là MAPD-CBS heuristic/limited-horizon conflict-based coordination.

### 14.5. Mục tiêu triển khai tối thiểu

MAPD-CBS solver tối thiểu cần:

- chạy online;
- không gọi `default_result()`;
- có task selection;
- có conflict avoidance tốt hơn Greedy;
- tránh target trùng không cần thiết;
- trả `env.result("MAPDCBSSolver", elapsed_sec)`.

---

# PHẦN C — Thiết kế thuật toán nên triển khai

## 15. Nguyên tắc chung cho cả 4 solver

Dù là Greedy, VRP, ACO hay MAPD-CBS, mỗi solver đều nên tuân thủ khung sau:

```text
1. start_time = time.time()
2. obs = env.reset()
3. while obs["done"] is False:
       actions = decide_actions(obs)
       obs, step_reward, done, info = env.step(actions)
4. return env.result(method_name, elapsed_sec)
```

Không nên:

- tự sinh đơn;
- tự sửa trực tiếp `env.orders`;
- tự cộng reward vào `env.total_reward`;
- dùng đơn chưa visible;
- gọi `default_result()` trong solver đã nộp chính thức.

---

## 16. Thứ tự ưu tiên cargo operation

Khi quyết định action cho một shipper, nên dùng ưu tiên:

```text
1. Nếu sau move sẽ ở điểm giao của đơn đang mang:
       chọn op = 2.
2. Nếu sau move sẽ ở điểm pickup của đơn đã chọn và không cần giao ngay:
       chọn op = 1.
3. Nếu chưa tới target:
       chọn op = 0.
```

Lưu ý:

- Nếu đang đứng ở điểm giao, nên delivery ngay vì delivery có reward và giải phóng capacity.
- Pickup chỉ nhặt 1 đơn nên cần cân nhắc có đáng pickup tại ô đó không.
- Nếu cùng một ô vừa có pickup vừa có delivery, đa số trường hợp nên ưu tiên delivery trước để giải phóng bag.

---

## 17. Hàm score order nên có

Một hàm score tốt là trái tim của solver.

### 17.1. Biến cần xét

Với một shipper `s` và một order `o` chưa pickup:

```text
d1 = khoảng cách từ shipper tới pickup
d2 = khoảng cách từ pickup tới delivery
arrival_pickup = t + d1
arrival_delivery = t + d1 + d2
slack = o.et - arrival_delivery
estimated_reward = reward nếu giao tại arrival_delivery
```

### 17.2. Ý tưởng score

Score nên tăng khi:

- `p` cao;
- estimated reward cao;
- `d1 + d2` thấp;
- còn kịp deadline;
- order nằm gần vùng có nhiều đơn mới;
- shipper đủ capacity.

Score nên giảm khi:

- không thể giao đúng hạn;
- distance quá xa;
- weight quá nặng so với W_max;
- pickup point gây lệch route lớn.

### 17.3. Score cho đơn đang mang

Với đơn trong `bag`, score delivery nên xét:

```text
d = distance từ shipper tới destination
arrival = t + d
slack = deadline - arrival
estimated_reward = reward nếu giao tại arrival
```

Nên ưu tiên đơn:

- có destination gần;
- deadline sắp tới;
- priority cao;
- cùng destination với nhiều đơn khác trong bag.

---

## 18. Hotspot/surge detection thực dụng

Phase 1 không công bố surge/hotspot, nhưng solver có thể tự quan sát.

Ý tưởng đơn giản:

```text
Mỗi timestep, lưu vị trí các new_order_ids.
Duy trì cửa sổ gần đây, ví dụ 30-60 timestep.
Đếm mật độ pickup theo vùng.
Nếu vùng nào xuất hiện nhiều đơn mới:
    xem là hotspot quan sát được.
    tăng score cho đơn gần đó.
    điều một số shipper rảnh/gần về vùng đó.
```

Không nên điều toàn bộ shipper vào cùng hotspot, vì dễ kẹt bottleneck.

---

## 19. Collision avoidance cơ bản

Env đã xử lý collision, nhưng solver nên tránh chủ động.

Một cách đơn giản:

```text
Sau khi mỗi shipper chọn move dự kiến:
    tạo reserved_next_cells.
    duyệt shipper theo độ ưu tiên:
        nếu next_cell chưa bị reserve:
            giữ move.
        nếu bị reserve:
            thử move thay thế làm giảm distance tới target.
        nếu không có move hợp lệ:
            S.
```

Nên tránh thêm edge swap:

```text
Không cho shipper A đi từ x→y trong khi shipper B đi từ y→x cùng timestep.
```

---

## 20. Lộ trình triển khai đề xuất

### Bước 1 — Chạy chắc Greedy BFS

Mục tiêu:

- Greedy chạy không lỗi trên 6 config.
- Có net_reward > 0.
- Kết quả lưu được vào `results/summary.json`.

Sau đó nâng cấp scoring.

### Bước 2 — Tách utility chung sang `solver.py`

Nên đưa BFS/score/helper vào `solver.py` để các solver dùng lại.

### Bước 3 — Implement VRP-like fallback

Trước khi dùng OR-Tools, nên có fallback không phụ thuộc thư viện ngoài.

Mục tiêu:

- VRP không còn 0.
- Có batch assignment khác Greedy.
- Có thể trình bày là rolling-horizon VRP heuristic nếu OR-Tools không có.

### Bước 4 — Implement ACO nhẹ

Mục tiêu:

- ACO không còn 0.
- Có pheromone table.
- Có heuristic score.
- Runtime thấp.

### Bước 5 — Implement MAPD-CBS lite

Mục tiêu:

- MAPD-CBS không còn 0.
- Có reservation/conflict avoidance rõ hơn Greedy.
- Có thể trình bày trong báo cáo.

### Bước 6 — Chạy benchmark và chọn method tốt nhất

Chạy:

```text
python run_test.py --config test_config.txt --out results --seed 42 --method all
```

Sau đó xem tổng điểm theo phương pháp trong summary.

Nếu Phase 2 cho chọn một method, chạy method tốt nhất:

```text
python run_test.py --config test_config.txt --out results_best --seed 42 --method <TênClassTốtNhất>
```

---

# PHẦN D — Checklist trước khi nộp

## 21. Checklist kỹ thuật

Trước khi nộp, kiểm tra:

- [ ] Thư mục `solvers/` có đúng 5 file cần thiết.
- [ ] Không đổi tên `greedy_bfs.py`, `vrp_ortools.py`, `aco_solver.py`, `mapd_cbs_solver.py`.
- [ ] Không đổi tên class `GreedyBFS`, `VRPOrToolsSolver`, `ACOSolver`, `MAPDCBSSolver`.
- [ ] Không sửa `env.py`.
- [ ] Không sửa `run_test.py`.
- [ ] Không sửa `test_config.txt`.
- [ ] 4 solver đều không gọi `default_result()` trong bản nộp cuối.
- [ ] 4 solver đều gọi `env.reset()` và `env.step()`.
- [ ] 4 solver đều trả kết quả bằng `env.result(...)`.
- [ ] Không dùng đơn tương lai.
- [ ] Không `pip install`.
- [ ] Không dùng internet khi chạy.
- [ ] Tổng runtime dưới 60 phút.

## 22. Checklist báo cáo

Báo cáo nên có:

- [ ] Thành viên và phân công.
- [ ] Mô tả bài toán online MAPD.
- [ ] Mô tả Greedy BFS.
- [ ] Mô tả VRP/OR-Tools hoặc VRP fallback.
- [ ] Mô tả ACO.
- [ ] Mô tả MAPD-CBS.
- [ ] Độ phức tạp thời gian/không gian từng thuật toán.
- [ ] Mức độ tối ưu: optimal/near-optimal/heuristic.
- [ ] Bảng kết quả 6 config.
- [ ] Net reward, delivery rate, on-time rate, runtime.
- [ ] Phân tích trade-off.
- [ ] Chiến lược xử lý surge/hotspot.

---

# PHẦN E — Đánh giá trạng thái hiện tại của bộ file bạn gửi

## 23. Trạng thái hiện tại

| File | Trạng thái | Cần làm tiếp |
|---|---|---|
| `env.py` | Môi trường online v3, không sửa | Chỉ đọc API |
| `run_test.py` | Grader v3, hỗ trợ `--method` | Không sửa |
| `test_config.txt` | 6 config Phase 1 mới | Không sửa |
| `solver.py` | Base class online đã đúng hướng | Nên thêm utility chung |
| `greedy_bfs.py` | Đã chạy online | Nâng cấp scoring |
| `vrp_ortools.py` | Skeleton | Cài rolling-horizon VRP |
| `aco_solver.py` | Skeleton | Cài ACO online nhẹ |
| `mapd_cbs_solver.py` | Skeleton | Cài CBS-lite/reservation |

## 24. Kết luận thực tế

Bộ file hiện tại đã sửa đúng phần khởi tạo để phù hợp env online, nhưng mới chỉ có Greedy BFS có thuật toán thật.

Để đạt yêu cầu bài, cần tiếp tục:

```text
1. Nâng cấp Greedy BFS.
2. Implement VRPOrToolsSolver.
3. Implement ACOSolver.
4. Implement MAPDCBSSolver.
5. Benchmark toàn bộ trên 6 config.
6. Viết báo cáo dựa trên kết quả thực nghiệm.
```

Nếu ưu tiên thời gian, nên làm theo hướng:

```text
Greedy mạnh trước → VRP fallback → MAPD-CBS lite → ACO nhẹ
```

Vì Greedy mạnh có thể là nền cho cả ba thuật toán còn lại.

---

## 25. Tóm tắt ngắn gọn để bắt tay vào triển khai

Bạn cần nhớ 5 ý chính:

1. Solver bây giờ là **online controller**, không phải offline simulator.
2. Mỗi bước chỉ quyết định action `(move, op)` cho từng shipper.
3. Env tự xử lý move, pickup, delivery, reward, cost, đơn mới.
4. Không được dùng đơn chưa xuất hiện.
5. Ba file `vrp_ortools.py`, `aco_solver.py`, `mapd_cbs_solver.py` hiện vẫn phải được implement thật để không bị 0.

