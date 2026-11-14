"""Two-proportion normal approximation and Wilson 95% CIs; descriptive, not causal proof."""
from math import erf, sqrt


def wilson(successes: int, total: int, z: float = 1.95996398454) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z*z / total
    center = (p + z*z/(2*total)) / denom
    half = z * sqrt((p*(1-p) + z*z/(4*total))/total)/denom
    return max(0.0, center-half), min(1.0, center+half)


def compare(control_conversions: int, control_users: int, treatment_conversions: int, treatment_users: int) -> dict:
    result = {"control": {"users": control_users, "conversions": control_conversions}, "treatment": {"users": treatment_users, "conversions": treatment_conversions}}
    for arm in ("control", "treatment"):
        n, k = result[arm]["users"], result[arm]["conversions"]
        result[arm]["rate"] = round(k/n, 6) if n else 0
        result[arm]["ci95"] = [round(v, 6) for v in wilson(k, n)]
    if not control_users or not treatment_users:
        return {**result, "p_value": None, "absolute_lift": None, "relative_lift": None, "warnings": ["Both arms require exposure data"]}
    pc, pt = control_conversions / control_users, treatment_conversions / treatment_users
    pool = (control_conversions + treatment_conversions) / (control_users + treatment_users)
    se = sqrt(pool*(1-pool)*(1/control_users+1/treatment_users))
    p_value = 2*(1-(1+erf(abs(pt-pc)/se/sqrt(2)))/2) if se else 1.0
    warnings = []
    if min(control_users, treatment_users) < 100:
        warnings.append("Small sample: normal approximation may be unreliable")
    if min(control_conversions, treatment_conversions, control_users-control_conversions, treatment_users-treatment_conversions) < 5:
        warnings.append("Sparse outcomes: use Fisher's exact test for formal inference")
    warnings.append("Observational rollout groups are not randomized experiments; do not infer causality")
    return {**result, "p_value": round(p_value, 6), "absolute_lift": round(pt-pc, 6), "relative_lift": round((pt-pc)/pc, 6) if pc else None, "warnings": warnings}
