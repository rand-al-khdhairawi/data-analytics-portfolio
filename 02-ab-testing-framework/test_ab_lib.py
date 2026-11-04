import numpy as np
from scipy import stats
import ab_lib as L

def test_z_equals_chi2():
    r = L.two_prop(260, 10000, 200, 10000)
    assert abs(r["z"] ** 2 - r["chi2"]) < 1e-9
    assert abs(r["p_z"] - r["p_chi2"]) < 1e-9

def test_ci_contains_diff_and_lift_sign():
    r = L.two_prop(300, 10000, 200, 10000)
    assert r["diff_ci"][0] < r["diff"] < r["diff_ci"][1]
    assert r["rel_lift"] > 0 and r["rel_lift_ci"][0] > 0

def test_srm_exact_split_passes_and_skew_fails():
    assert L.srm_test([960, 40], [0.96, 0.04])["p"] > 0.9
    assert L.srm_test([5000, 5400], [0.5, 0.5])["p"] < 0.001

def test_power_and_mde_consistent():
    mde = L.mde_two_prop(0.02, 50000, 50000)
    assert abs(L.power_two_prop(0.02, 0.02 + mde, 50000, 50000) - 0.8) < 0.02
    n = L.n_per_group(0.02, 0.004)
    assert abs(L.power_two_prop(0.02, 0.024, n, n) - 0.8) < 0.01

def test_logit_recovers_coefficients():
    rng = np.random.default_rng(1)
    x = rng.normal(size=200000); g = rng.integers(0, 2, 200000)
    p = 1 / (1 + np.exp(-(-2 + 0.5 * g + 0.8 * x)))
    y = rng.random(200000) < p
    f = L.logit_fit(np.column_stack([np.ones_like(x), g, x]), y, ["c", "g", "x"])
    assert np.allclose(f["coef"], [-2, 0.5, 0.8], atol=0.03)

def test_cmh_matches_single_stratum_or():
    a, b, c, d = 30, 970, 20, 980
    r = L.cmh([(a, b, c, d)])
    assert abs(r["or_mh"] - (a * d) / (b * c)) < 1e-9

def test_holm_monotone_and_bounded():
    adj = L.holm([0.01, 0.04, 0.03, 0.5])
    assert (adj >= np.array([0.01, 0.04, 0.03, 0.5])).all() and adj.max() <= 1
