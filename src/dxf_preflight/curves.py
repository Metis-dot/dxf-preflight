"""Analytic measurements only; curves never enter the straight-segment graph.

Default-OCS geometry is validated by the caller. No DXF mutation, tessellation,
block transformation, intersection, duplicate or contour classification occurs.
"""

from fractions import Fraction
import math


class CurveMeasurementError(ValueError):
    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule


def measure_curve(kind: str, center: tuple[float, float], radius: float,
                  start_angle: float | None = None, end_angle: float | None = None) -> dict:
    """Measure parsed XY values, rejecting non-finite/degenerate/range-loss data.

    Bounds and lengths are approximate floating-point display values, not
    interval-certified enclosures. Angle normalization/cardinal inclusion use
    exact fractions of parsed floats to avoid wrap/subtraction ambiguity.
    """
    if kind not in {"CIRCLE", "ARC"}:
        raise ValueError("Only CIRCLE and ARC measurements are supported")
    values = (*center, radius) + ((start_angle, end_angle) if kind == "ARC" else ())
    if not all(math.isfinite(v) for v in values):
        raise CurveMeasurementError("GEOM001", "Non-finite curve coordinates or attributes; no measurement.")
    if radius <= 0:
        raise CurveMeasurementError("GEOM002", "Curve radius must be strictly positive; no measurement.")
    # Refuse overflow or coordinate collapse rather than displaying a tiny
    # curve at a huge center as a zero-width object. This is a conservative
    # range guard, not a bound on all remaining rounding error.
    extremes = [(value - radius, value + radius) for value in center]
    if not all(math.isfinite(v) for pair in extremes for v in pair) or not all(
        low < value < high for value, (low, high) in zip(center, extremes)
    ):
        raise CurveMeasurementError("SCOPE007", "Curve bounds overflow or radius is unresolved at the center's numeric scale; no measurement.")
    result = {
        "center": list(center), "radius": radius,
        "length_is_approximate": True, "bounds_are_approximate": True,
    }
    if kind == "CIRCLE":
        result["length"] = radius * math.tau
        result["bounds"] = {"minimum": [p[0] for p in extremes], "maximum": [p[1] for p in extremes]}
    else:
        # DXF ARC runs counter-clockwise around the default +Z extrusion.
        start = Fraction(start_angle) % 360
        end = Fraction(end_angle) % 360
        sweep = (end - start) % 360
        if sweep == 0:
            raise CurveMeasurementError("GEOM002", "Equal normalized ARC angles are ambiguous/degenerate; neither zero length nor a full circle is inferred.")
        normalized = (float(start), float(end), float(sweep))
        if not all(0 <= v < 360 for v in normalized) or normalized[2] <= 0:
            raise CurveMeasurementError("SCOPE007", "ARC angle normalization loses the nonzero sweep at floating-point precision; no measurement.")

        def point(angle):
            # Exact cardinal trig values avoid artificial 1e-16 offsets on
            # horizontal/vertical endpoints; other trig values are approximate.
            cardinal = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
            cosine, sine = cardinal.get(angle, (None, None))
            if cosine is None:
                radians = math.radians(float(angle))
                cosine, sine = math.cos(radians), math.sin(radians)
            return [center[0] + radius * cosine, center[1] + radius * sine]

        first, last = point(start), point(end)
        if first == last:
            raise CurveMeasurementError("SCOPE007", "ARC endpoints collapse at floating-point precision; no measurement.")
        candidates = [first, last]
        candidates.extend(point(Fraction(angle)) for angle in (0, 90, 180, 270)
                          if (angle - start) % 360 <= sweep)
        result.update({
            "start_angle_degrees": start_angle, "end_angle_degrees": end_angle,
            "normalized_start_angle_degrees": normalized[0], "normalized_end_angle_degrees": normalized[1],
            "counterclockwise_sweep_degrees": normalized[2],
            "start": first, "end": last, "endpoints_are_approximate": True,
            "length": radius * math.radians(normalized[2]),
            "bounds": {"minimum": [min(p[i] for p in candidates) for i in (0, 1)],
                       "maximum": [max(p[i] for p in candidates) for i in (0, 1)]},
        })
    derived = (result["length"], *result["bounds"]["minimum"], *result["bounds"]["maximum"])
    if not all(math.isfinite(v) for v in derived) or result["length"] <= 0:
        raise CurveMeasurementError("SCOPE007", "Curve derived length/bounds overflow or underflow; no measurement.")
    return result
