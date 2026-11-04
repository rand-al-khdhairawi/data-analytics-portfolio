"""Statistical helpers for the A/B analysis (NumPy and SciPy only)."""
import numpy as np
import pandas as pd
from scipy import stats

Z975 = stats.norm.ppf(0.975)

def srm_test(observed, expected_props):
    """Chi-square goodness-of-fit of observed group sizes against the intended allocation."""
    observed = np.asarray(observed, float)
    exp = np.asarray(expected_props, float) * observed.sum()
    chi2 = ((observed - exp) ** 2 / exp).sum()
    return {"chi2": float(chi2), "p": float(stats.chi2.sf(chi2, len(observed) - 1))}

def two_prop(x1, n1, x2, n2):
    """Treatment (1) vs control (2): z-test, chi-square, CI for the difference and for the relative lift."""
    p1, p2 = x1 / n1, x2 / n2
    pool = (x1 + x2) / (n1 + n2)
    se_pool = np.sqrt(pool * (1 - pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se_pool
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p1 - p2
    # relative lift: delta method on log(p1/p2)
    se_log = np.sqrt((1 - p1) / (n1 * p1) + (1 - p2) / (n2 * p2))
    ratio = p1 / p2
    chi2, p_chi, _, _ = stats.chi2_contingency([[x1, n1 - x1], [x2, n2 - x2]], correction=False)
    return {"p_treat": p1, "p_ctrl": p2, "diff": diff, "diff_ci": (diff - Z975 * se, diff + Z975 * se),
            "rel_lift": ratio - 1, "rel_lift_ci": (np.exp(np.log(ratio) - Z975 * se_log) - 1, np.exp(np.log(ratio) + Z975 * se_log) - 1),
            "z": float(z), "p_z": float(2 * stats.norm.sf(abs(z))), "chi2": float(chi2), "p_chi2": float(p_chi)}

def wilson(x, n):
    p = x / n; d = 1 + Z975 ** 2 / n
    c = (p + Z975 ** 2 / (2 * n)) / d
    h = Z975 * np.sqrt(p * (1 - p) / n + Z975 ** 2 / (4 * n ** 2)) / d
    return c - h, c + h

def power_two_prop(p_ctrl, p_treat, n_ctrl, n_treat, alpha=0.05):
    se = np.sqrt(p_ctrl * (1 - p_ctrl) / n_ctrl + p_treat * (1 - p_treat) / n_treat)
    za = stats.norm.ppf(1 - alpha / 2)
    return float(stats.norm.sf(za - abs(p_treat - p_ctrl) / se) + stats.norm.cdf(-za - abs(p_treat - p_ctrl) / se))

def mde_two_prop(p_ctrl, n_ctrl, n_treat, alpha=0.05, power=0.8):
    """Smallest absolute lift detectable with the given power, solved against power_two_prop."""
    from scipy.optimize import brentq
    f = lambda d: power_two_prop(p_ctrl, p_ctrl + d, n_ctrl, n_treat, alpha) - power
    return float(brentq(f, 1e-9, 1 - p_ctrl - 1e-9))

def n_per_group(p_ctrl, lift_abs, alpha=0.05, power=0.8):
    p2 = p_ctrl + lift_abs; pbar = (p_ctrl + p2) / 2
    za, zb = stats.norm.ppf(1 - alpha / 2), stats.norm.ppf(power)
    return int(np.ceil(((za * np.sqrt(2 * pbar * (1 - pbar)) + zb * np.sqrt(p_ctrl * (1 - p_ctrl) + p2 * (1 - p2))) ** 2) / lift_abs ** 2))

def logit_fit(X, y, names, max_iter=50):
    """Logistic regression by Newton-Raphson. Returns coefficients, standard errors, p-values, log-likelihood."""
    X = np.asarray(X, float); y = np.asarray(y, float)
    b = np.zeros(X.shape[1]); b[0] = np.log(y.mean() / (1 - y.mean()))
    for _ in range(max_iter):
        eta = X @ b; mu = 1 / (1 + np.exp(-eta))
        grad = X.T @ (y - mu)
        W = mu * (1 - mu)
        H = (X * W[:, None]).T @ X
        step = np.linalg.solve(H, grad)
        b = b + step
        if np.abs(step).max() < 1e-9: break
    mu = 1 / (1 + np.exp(-(X @ b)))
    cov = np.linalg.inv((X * (mu * (1 - mu))[:, None]).T @ X)
    se = np.sqrt(np.diag(cov))
    ll = float((y * np.log(mu) + (1 - y) * np.log(1 - mu)).sum())
    z = b / se
    return {"names": names, "coef": b, "se": se, "p": 2 * stats.norm.sf(np.abs(z)), "ll": ll,
            "or": np.exp(b), "or_ci": (np.exp(b - Z975 * se), np.exp(b + Z975 * se))}

def lr_test(ll_full, ll_reduced, df):
    stat = 2 * (ll_full - ll_reduced)
    return {"stat": float(stat), "p": float(stats.chi2.sf(stat, df))}

def cmh(strata):
    """Mantel-Haenszel pooled odds ratio and CMH chi-square. strata: list of (a, b, c, d) =
    (treat converted, treat not, ctrl converted, ctrl not)."""
    num = den = 0.0; sa = ea = va = 0.0
    for a, b, c, d in strata:
        n = a + b + c + d
        if n < 2: continue
        num += a * d / n; den += b * c / n
        n1, m1 = a + b, a + c
        sa += a; ea += n1 * m1 / n
        va += (a + b) * (c + d) * (a + c) * (b + d) / (n ** 2 * (n - 1))
    chi2 = (abs(sa - ea) - 0.5) ** 2 / va
    return {"or_mh": num / den, "chi2": float(chi2), "p": float(stats.chi2.sf(chi2, 1))}

def holm(pvals):
    p = np.asarray(pvals, float); order = np.argsort(p); m = len(p)
    adj = np.empty(m); running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i]); adj[i] = min(1.0, running)
    return adj
