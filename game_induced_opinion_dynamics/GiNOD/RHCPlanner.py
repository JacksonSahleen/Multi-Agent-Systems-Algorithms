"""
RHCPlanner.py

This file contains the RHCPlanner for Receding horizon
control planner for two-player games.
"""

import numpy as np
from qmdp import QMDP

class RHCPlanner(object):
	"""
	Receding horizon control planner for two-player games.

	Attributes:
	- xs (np.ndarray): state trajectory.
	- zs (np.ndarray): opinion trajectory.
	- Hs (np.ndarray): Hessian matrices.
	- PoI (np.ndarray): PoI values.
	"""

	def __init__(self, subgames, N_sim, ph_sys, ph_sys_casadi,
				 GiNOD, look_ahead, a_bounds, w_bounds,
				 method='QMDPL0', W_ctrl=None):
		"""
		Initializer.

		Args:
		- subgames (list): list of subgame solvers.
		- N_sim (int): number of simulation steps.
		- ph_sys (object): physical system.
		- ph_sys_casadi (object): CasADi physical system.
		- GiNOD (object): GiNOD object.
		- look_ahead (int): look-ahead horizon.
		- a_bounds (list): action bounds.
		- w_bounds (list): disturbance bounds.
		- method (str): method to use for planning.
		- W_ctrl (list): control weights.
		"""

		self._subgames = subgames
		self._N_sim = N_sim
		self._ph_sys = ph_sys
		self._GiNOD = GiNOD
		self._method = method
		self._QMDP_P1 = QMDP(ph_sys_casadi, GiNOD, W_ctrl[0], player_id=1,
							 look_ahead=look_ahead, a_bounds=a_bounds, w_bounds=w_bounds)
		self._QMDP_P2 = QMDP(ph_sys_casadi, GiNOD, W_ctrl[1], player_id=2,
							 look_ahead=look_ahead, a_bounds=a_bounds, w_bounds=w_bounds)
		self._look_ahead = look_ahead

		self.xs = None
		self.zs = None
		self.Hs = None
		self.PoI = None

	def plan(self, x0, z0):
		"""
		Receding horizon planning.
		Assumes two player.

		Args:
		- x0 (np.ndarray): initial state
		- z0 (np.ndarray): initial opinion
		"""

		# Initialization.
		nx = len(x0)
		nz = len(z0)
		nz1 = self._GiNOD._num_opn_P1
		nz2 = self._GiNOD._num_opn_P2

		xs = np.zeros((nx, self._N_sim + 1))
		zs = np.zeros((nz, self._N_sim + 1))
		xs[:, 0] = x0
		zs[:, 0] = z0

		Hs = np.zeros((nz1 + nz2, nz1 + nz2, self._N_sim))
		PoI = np.zeros((2, self._N_sim))

		for k in range(self._N_sim):
			# Initialize subgame information.
			Z1_k = np.zeros((nx, nx, nz1, nz2))
			Z2_k = np.zeros((nx, nx, nz1, nz2))
			zeta1_k = np.zeros((nx, nz1, nz2))
			zeta2_k = np.zeros((nx, nz1, nz2))
			nom_cost1_k = np.zeros((2, 2))
			nom_cost2_k = np.zeros((2, 2))
			xnom_k = np.zeros((nx, nz1, nz2))

			# Solve subgames and collect subgame information.
			for l1 in range(nz1):
				for l2 in range(nz2):
					solver = self._subgames[l1][l2]
					solver.run(xs[:, k])    # solves the subgame.
					xs_ILQ = np.asarray(solver._best_operating_point[0])
					xnom_k[:, l1, l2] = xs_ILQ[:, self._look_ahead]
					Zs = np.asarray(solver._best_operating_point[4])[:, :, :, 0]
					zetas = np.asarray(solver._best_operating_point[5])[:, :, 0]
					nom_costs = np.asarray(solver._best_operating_point[6])
					Z1_k[:, :, l1, l2] = Zs[0, :, :]
					Z2_k[:, :, l1, l2] = Zs[1, :, :]
					zeta1_k[:, l1, l2] = zetas[0, :]
					zeta2_k[:, l1, l2] = zetas[1, :]
					nom_cost1_k[l1, l2] = nom_costs[0]
					nom_cost2_k[l1, l2] = nom_costs[1]

					if k == 0:
						print('[RHC] Subgame', l1, l2, 'compiled.')

			if k == 0:
				znom1_k = z0[:nz1]
				znom2_k = z0[nz1:nz1 + nz2]
			else:
				znom1_k = zs[:nz1, k - 1]
				znom2_k = zs[nz1:nz1 + nz2, k - 1]

			z1_k = zs[:nz1, k]
			z2_k = zs[nz1:nz1 + nz2, k]
			att1_k = zs[nz1 + nz2:nz1 + nz2 + 1, k]
			att2_k = zs[-1, k]

			subgame_k = (Z1_k, Z2_k, zeta1_k, zeta2_k, xnom_k, znom1_k, znom2_k, nom_cost1_k, nom_cost2_k)

			# Solves QMDP based on current subgames and opinion states.
			if self._method == 'QMDPL0':
				# Player 1
				u1 = self._QMDP_P1.plan_level_0(xs[:, k], z1_k, z2_k, self._subgames)
				# Player 2
				u2 = self._QMDP_P2.plan_level_0(xs[:, k], z2_k, z1_k, self._subgames)

			elif self._method == 'QMDPL1':
				# Player 1
				u1 = self._QMDP_P1.plan_level_1(
					xs[:, k], z1_k, z2_k, att1_k, att2_k, self._subgames, subgame_k
				)
				# Player 2
				u2 = self._QMDP_P2.plan_level_1(
					xs[:, k], z2_k, z1_k, att2_k, att1_k, self._subgames, subgame_k
				)

			elif self._method == 'QMDPL1L0':
				# Player 1
				u1 = self._QMDP_P1.plan_level_1(
					xs[:, k], z1_k, z2_k, att1_k, att2_k, self._subgames, subgame_k
				)
				# Player 2
				u2 = self._QMDP_P2.plan_level_0(xs[:, k], z2_k, z1_k, self._subgames)

			else:
				raise NotImplementedError

			u_list = [u1, u2]

			# Evolves GiNOD.
			x_jnt = np.hstack((xs[:, k], zs[:, k]))

			z_dot_k, H_k, PoI1_k, PoI2_k = self._GiNOD.cont_time_dyn(x_jnt, None, subgame_k)

			zs[:, k + 1] = zs[:, k] + self._GiNOD._T * np.asarray(z_dot_k)
			Hs[:, :, k] = np.asarray(H_k)
			PoI[:, k] = np.array((PoI1_k, PoI2_k))

			# Evolve states of physical system.
			x_ph_next = self._ph_sys.disc_time_dyn(xs[:, k], u_list)
			xs[:, k + 1] = np.asarray(x_ph_next)

			print(k, np.round(zs[:, k], 2), PoI1_k, PoI2_k)

		# Save data.
		self.xs = xs
		self.zs = zs
		self.Hs = Hs
		self.PoI = PoI
