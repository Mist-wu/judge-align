"""Dependency-free ordinal agreement and paired cluster bootstrap statistics."""
import math
import random
from collections import defaultdict


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + 1 + j) / 2
        for k in range(i, j):
            out[order[k]] = rank
        i = j
    return out


def pearson(x, y):
    if len(x) != len(y):
        raise ValueError("Paired vectors must have equal length")
    if len(x) < 2:
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    xx, yy = sum((v-mx)**2 for v in x), sum((v-my)**2 for v in y)
    if xx < 1e-20 or yy < 1e-20:
        return None
    return sum((a-mx)*(b-my) for a, b in zip(x, y)) / math.sqrt(xx*yy)


def spearman(x, y):
    return pearson(ranks(x), ranks(y))


def qwk(x, y):
    if len(x) != len(y) or not x:
        return None
    if any(type(v) is not int or not 1 <= v <= 5 for v in [*x, *y]):
        raise ValueError("QWK requires integer ratings in 1..5")
    observed = sum((a-b)**2 for a, b in zip(x, y)) / len(x)
    cx = [x.count(i) for i in range(1, 6)]
    cy = [y.count(i) for i in range(1, 6)]
    expected = sum(cx[i]*cy[j]*(i-j)**2 for i in range(5) for j in range(5)) / len(x)**2
    return None if not expected else 1 - observed/expected


def partial_spearman(scores, lengths, human_quality):
    """Residual rank correlation after linear control for human quality rank.

    Human quality, not judge quality, is required. This is associational, not
    causal; no estimate is emitted when the control or a residual is constant.
    """
    if not (len(scores) == len(lengths) == len(human_quality)) or len(scores) < 4:
        return None
    x, y, z = ranks(scores), ranks(lengths), ranks(human_quality)
    mz = sum(z)/len(z)
    zz = sum((v-mz)**2 for v in z)
    if not zz:
        return None
    def residual(v):
        mean = sum(v)/len(v)
        beta = sum((a-mean)*(b-mz) for a,b in zip(v,z))/zz
        return [a-mean-beta*(b-mz) for a,b in zip(v,z)]
    return pearson(residual(x), residual(y))


def quantile(values, p):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values)-1)*p
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] + (values[hi]-values[lo])*(pos-lo)


def cluster_ci(rows, metric, cluster_key="context_id", rounds=1000, seed=42):
    if rounds < 1:
        raise ValueError("Bootstrap rounds must be positive")
    groups = defaultdict(list)
    for row in rows:
        groups[row[cluster_key]].append(row)
    point = metric(rows) if rows else None
    if len(groups) < 2:
        return {"value": point, "ci95": None, "n": len(rows), "clusters": len(groups), "valid_resamples": 0}
    values = list(groups.values())
    rng = random.Random(seed)
    samples = []
    for _ in range(rounds):
        sampled = [row for _ in values for row in rng.choice(values)]
        value = metric(sampled)
        if value is not None and math.isfinite(value):
            samples.append(value)
    return {"value": point, "ci95": [quantile(samples,.025),quantile(samples,.975)] if samples else None,
            "n": len(rows), "clusters": len(groups), "valid_resamples": len(samples),
            "bootstrap_rounds": rounds, "seed": seed}


def mean(values):
    return sum(values)/len(values) if values else None


def canonical_winner(value, swapped):
    if value == "tie":
        return "tie"
    if value not in {"A", "B"}:
        raise ValueError("Invalid pairwise winner")
    return ({"A":"B", "B":"A"}[value] if swapped else value)
