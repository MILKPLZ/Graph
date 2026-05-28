"""Basic versions of the four main competition solver families."""

from solver_baseline.aco_solver import ACOSolver
from solver_baseline.greedy_bfs import GreedyBFS
from solver_baseline.mapd_cbs_solver import MAPDCBSSolver
from solver_baseline.vrp_ortools import VRPOrToolsSolver

BASELINE_SOLVERS = [
    GreedyBFS,
    VRPOrToolsSolver,
    ACOSolver,
    MAPDCBSSolver,
]
