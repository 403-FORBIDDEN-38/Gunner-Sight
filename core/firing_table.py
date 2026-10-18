"""
弹道角度-距离预测模块。PCHIP + 多分支。
"""
from __future__ import annotations


def _pchip_end_slope(h0, h1, delta0, delta1):
    d = ((2.0 * h0 + h1) * delta0 - h0 * delta1) / (h0 + h1)
    if d * delta0 <= 0.0:
        return 0.0
    if delta0 * delta1 < 0.0 and abs(d) > abs(3.0 * delta0):
        return 3.0 * delta0
    return d


def _pchip_derivatives(x, y):
    n = len(x)
    if n == 1:
        return [0.0]
    if n == 2:
        s = (y[1] - y[0]) / (x[1] - x[0]) if x[1] != x[0] else 0.0
        return [s, s]
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    delta = [(y[i + 1] - y[i]) / h[i] if h[i] != 0 else 0.0 for i in range(n - 1)]
    d = [0.0] * n
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] > 0.0:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            d[i] = (w1 + w2) / (w1 / delta[i - 1] + w2 / delta[i])
        else:
            d[i] = 0.0
    d[0] = _pchip_end_slope(h[0], h[1], delta[0], delta[1])
    d[n - 1] = _pchip_end_slope(h[n - 2], h[n - 3], delta[n - 2], delta[n - 3])
    return d


def _hermite_interp(x0, x1, y0, y1, d0, d1, xq):
    h = x1 - x0
    if h == 0.0:
        return y0
    t = (xq - x0) / h
    t2 = t * t
    t3 = t2 * t
    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    return h00 * y0 + h10 * h * d0 + h01 * y1 + h11 * h * d1


class Branch:
    def __init__(self, name, samples):
        self.name = name
        seen = {}
        for s in samples:
            a = float(s["angle"])
            d = float(s["distance"])
            seen[a] = d
        self.angles = sorted(seen.keys())
        self.distances = [seen[a] for a in self.angles]
        self._derivs = _pchip_derivatives(self.angles, self.distances) if len(self.angles) >= 2 else None

    @property
    def min_angle(self):
        return self.angles[0] if self.angles else 0.0

    @property
    def max_angle(self):
        return self.angles[-1] if self.angles else 0.0

    def contains(self, angle):
        if not self.angles:
            return False
        return self.min_angle <= angle <= self.max_angle

    # 外推范围限制（超出标定范围 ±15° 内才外推，再远返回 None）
    EXTRAPOLATE_LIMIT = 15.0

    def query(self, angle):
        if len(self.angles) == 0:
            return None
        if len(self.angles) == 1:
            return self.distances[0]
        if self.contains(angle):
            lo, hi = 0, len(self.angles) - 1
            while lo < hi - 1:
                mid = (lo + hi) // 2
                if self.angles[mid] <= angle:
                    lo = mid
                else:
                    hi = mid
            return _hermite_interp(self.angles[lo], self.angles[hi], self.distances[lo], self.distances[hi], self._derivs[lo], self._derivs[hi], angle)
        # 外推：边界切线线性外推
        if angle < self.min_angle:
            if self.min_angle - angle > self.EXTRAPOLATE_LIMIT:
                return None
            return self.distances[0] + self._derivs[0] * (angle - self.angles[0])
        else:
            if angle - self.max_angle > self.EXTRAPOLATE_LIMIT:
                return None
            return self.distances[-1] + self._derivs[-1] * (angle - self.angles[-1])

    def can_extrapolate(self, angle):
        """角度是否在外推范围内（不含标定范围内）。"""
        if not self.angles or self.contains(angle):
            return False
        if angle < self.min_angle:
            return self.min_angle - angle <= self.EXTRAPOLATE_LIMIT
        return angle - self.max_angle <= self.EXTRAPOLATE_LIMIT

    def to_dict(self):
        return {"name": self.name, "samples": [{"angle": a, "distance": d} for a, d in zip(self.angles, self.distances)]}


class BallisticProfile:
    def __init__(self, pitch_range=None, branches=None, physics=None):
        self.pitch_range = pitch_range
        self.branches = branches or []
        self.physics = physics or {}

    @classmethod
    def from_config(cls, data):
        if data is None:
            return cls()
        if isinstance(data, dict) and "branches" in data:
            pitch_range = tuple(data["pitch_range"]) if data.get("pitch_range") else None
            branches = [Branch(b["name"], b.get("samples", [])) for b in data.get("branches", [])]
            physics = data.get("physics", {})
            return cls(pitch_range, branches, physics)
        if isinstance(data, list):
            samples = []
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    samples.append({"angle": float(item[0]), "distance": float(item[1])})
                elif isinstance(item, dict):
                    samples.append({"angle": float(item["angle"]), "distance": float(item["distance"])})
            if samples:
                return cls(branches=[Branch("默认", samples)])
            return cls()
        return cls()

    def to_config(self):
        return {"pitch_range": list(self.pitch_range) if self.pitch_range else None, "branches": [b.to_dict() for b in self.branches], "physics": self.physics}

    def query(self, angle):
        # 优先用标定范围内的分支
        candidates = [b for b in self.branches if b.contains(angle)]
        if not candidates:
            # 范围内没有，尝试外推范围内的分支
            candidates = [b for b in self.branches if b.can_extrapolate(angle)]
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0].query(angle)
        results = [b.query(angle) for b in candidates]
        results = [r for r in results if r is not None]
        return max(results) if results else None

    def is_extrapolation(self, angle):
        return not any(b.contains(angle) for b in self.branches)


def query_distance(firing_table_data, angle):
    profile = BallisticProfile.from_config(firing_table_data)
    return profile.query(angle)


def is_extrapolation(firing_table_data, angle):
    profile = BallisticProfile.from_config(firing_table_data)
    return profile.is_extrapolation(angle)
