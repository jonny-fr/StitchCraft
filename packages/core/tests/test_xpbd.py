import numpy as np
from stitchcraft_core.sim.xpbd import DihedralGroup, dihedral_angle_and_grad


def quad(fold: float):
    # edge along x from x3=(0,0,0) to x4=(1,0,0); wings in +y and folded -y
    x = np.array(
        [
            [0.5, 1.0, 0.0],
            [0.5, -np.cos(fold), np.sin(fold)],
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
        ]
    )
    idx = np.array([[2, 3, 0, 1]])  # (i, j, k, l): edge i-j, wings k, l
    return x, idx


def test_flat_quad_has_zero_angle():
    x, idx = quad(0.0)
    theta, _ = dihedral_angle_and_grad(x, idx)
    assert abs(theta[0]) < 1e-12


def test_angle_sign_follows_fold_direction():
    up, idx = quad(0.5)
    down, _ = quad(-0.5)
    a, _ = dihedral_angle_and_grad(up, idx)
    b, _ = dihedral_angle_and_grad(down, idx)
    assert np.isclose(a[0], -b[0]) and abs(a[0]) > 0.4


def test_gradient_matches_finite_differences():
    rng = np.random.default_rng(1)
    x, idx = quad(0.7)
    x = x + rng.normal(scale=0.05, size=x.shape)
    theta, grad = dihedral_angle_and_grad(x, idx)
    h = 1e-6
    for col in range(4):
        for axis in range(3):
            xp = x.copy()
            xp[idx[0, col], axis] += h
            tp, _ = dihedral_angle_and_grad(xp, idx)
            num = (tp[0] - theta[0]) / h
            assert np.isclose(grad[0, col, axis], num, atol=1e-4), (col, axis)


def test_dihedral_group_restores_rest_angle():
    x, idx = quad(0.9)
    group = DihedralGroup(idx, np.zeros(1), np.asarray(0.0))
    w = np.ones(4)
    for _ in range(50):
        group.lam[:] = 0
        group.project(x, w, 1 / 60)
    theta, _ = dihedral_angle_and_grad(x, idx)
    assert abs(theta[0]) < 1e-3


def test_collision_ignores_inactive_particles():
    from stitchcraft_core.sim.xpbd import Collision

    x = np.array([[0.0, 0, 0], [0.1, 0, 0], [5.0, 0, 0]])
    coll = Collision(1.0, np.zeros(0, dtype=np.int64))
    assert coll.group(x, np.array([True, False, True])) is None
    assert coll.group(x, np.array([True, True, True])) is not None
