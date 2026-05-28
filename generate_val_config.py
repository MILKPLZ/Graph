import random

def generate_map(N, map_type='random', obstacle_ratio=0.2):
    grid = [[0 for _ in range(N)] for _ in range(N)]
    
    if map_type == 'empty':
        # Even for empty, add borders to avoid out-of-bounds just in case, though the env logic handles it.
        for i in range(N):
            grid[0][i] = 1
            grid[N-1][i] = 1
            grid[i][0] = 1
            grid[i][N-1] = 1
    elif map_type == 'borders':
        for i in range(N):
            grid[0][i] = 1
            grid[N-1][i] = 1
            grid[i][0] = 1
            grid[i][N-1] = 1
    elif map_type == 'random':
        for i in range(1, N-1):
            for j in range(1, N-1):
                if random.random() < obstacle_ratio:
                    grid[i][j] = 1
        for i in range(N):
            grid[0][i] = 1
            grid[N-1][i] = 1
            grid[i][0] = 1
            grid[i][N-1] = 1
    elif map_type == 'maze':
        for i in range(N):
            grid[0][i] = 1
            grid[N-1][i] = 1
            grid[i][0] = 1
            grid[i][N-1] = 1
        for i in range(2, N-2, 3):
            for j in range(1, N-1):
                # Create some holes for passage
                if j != N//2 and j != N//4 and j != 3*N//4:
                    grid[i][j] = 1
    elif map_type == 'city':
        # Grid city blocks
        for i in range(N):
            grid[0][i] = 1
            grid[N-1][i] = 1
            grid[i][0] = 1
            grid[i][N-1] = 1
        for i in range(3, N-3, 4):
            for j in range(3, N-3, 4):
                grid[i][j] = 1
                grid[i+1][j] = 1
                grid[i][j+1] = 1
                grid[i+1][j+1] = 1
                
    # Ensure starting positions are available by clearing some corners inside the border
    grid[1][1] = 0
    grid[1][N-2] = 0
    grid[N-2][1] = 0
    grid[N-2][N-2] = 0
    grid[N//2][N//2] = 0
    return grid

configs = []

# 1. Micro - Traffic Jam (N=15, C=25)
configs.append({
    'name': 'V_TrafficJam',
    'N': 15, 'C': 25, 'G': 500, 'T': 500,
    'K_max': [3]*25,
    'W_max': [20.0]*25,
    'map': generate_map(15, 'empty')
})

# 2. Medium - Sparse Random (N=30, C=10)
configs.append({
    'name': 'V_MediumSparse',
    'N': 30, 'C': 10, 'G': 300, 'T': 800,
    'K_max': [3]*10,
    'W_max': [30.0]*10,
    'map': generate_map(30, 'random', 0.15)
})

# 3. Bottleneck Maze (N=50, C=15)
configs.append({
    'name': 'V_Maze',
    'N': 50, 'C': 15, 'G': 800, 'T': 1200,
    'K_max': [2]*15,
    'W_max': [25.0]*15,
    'map': generate_map(50, 'maze')
})

# 4. Large City (N=70, C=20)
configs.append({
    'name': 'V_City',
    'N': 70, 'C': 20, 'G': 1000, 'T': 1800,
    'K_max': [3]*20,
    'W_max': [30.0]*20,
    'map': generate_map(70, 'city')
})

# 5. Huge Endurance (N=100, C=25, Max limits)
configs.append({
    'name': 'V_Endurance',
    'N': 100, 'C': 25, 'G': 1500, 'T': 2400,
    'K_max': [3]*25,
    'W_max': [40.0]*25,
    'map': generate_map(100, 'random', 0.1)
})

# 6. Explicit Surge and Hotspots
configs.append({
    'name': 'V_SurgeHotspot',
    'N': 40, 'C': 20, 'G': 1200, 'T': 1000,
    'K_max': [3]*20,
    'W_max': [20.0]*20,
    'surge_windows': '100 200 400 500 700 800',
    'hotspots': '10 10 30 30 20 20',
    'surge_amplitude': '4.0',
    'map': generate_map(40, 'borders')
})

with open('val_config.txt', 'w') as f:
    f.write("[SEED]\nbase_seed = 42\n\n")
    for cfg in configs:
        f.write(f"[CONFIG]\n")
        f.write(f"name    = {cfg['name']}\n")
        f.write(f"N       = {cfg['N']}\n")
        f.write(f"C       = {cfg['C']}\n")
        f.write(f"G       = {cfg['G']}\n")
        f.write(f"T       = {cfg['T']}\n")
        f.write(f"K_max   = {' '.join(map(str, cfg['K_max']))}\n")
        f.write(f"W_max   = {' '.join(map(str, cfg['W_max']))}\n")
        
        if 'surge_windows' in cfg:
            f.write(f"surge_windows = {cfg['surge_windows']}\n")
            f.write(f"hotspots      = {cfg['hotspots']}\n")
            f.write(f"surge_amplitude = {cfg['surge_amplitude']}\n")
            
        f.write("[MAP]\n")
        for row in cfg['map']:
            f.write(" ".join(map(str, row)) + "\n")
        f.write("[END]\n\n")

print("Generated val_config.txt successfully.")
