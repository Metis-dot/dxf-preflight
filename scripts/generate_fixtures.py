"""Generate original synthetic drawings; no customer/factory data is used."""

from pathlib import Path
import ezdxf

ROOT = Path(__file__).resolve().parents[1]


def rectangle(doc):
    points = [(0, 0), (40, 0), (40, 20), (0, 20)]
    for a, b in zip(points, points[1:] + points[:1]):
        doc.modelspace().add_line(a, b)


def generate():
    names = ["rectangle_lines", "rectangle_polyline", "open_chain", "duplicate_reverse", "unitless", "unsupported_arc", "bulged_polyline", "block_insert", "tolerance_gap", "self_crossing", "non_xy_line", "intersecting_rectangles", "interior_endpoint_contact", "collinear_overlap", "parallel_disjoint"]
    for name in names:
        doc = ezdxf.new("R2010")
        doc.units = 0 if name == "unitless" else 4
        msp = doc.modelspace()
        if name in {"rectangle_lines", "duplicate_reverse", "unitless", "unsupported_arc", "block_insert", "tolerance_gap", "non_xy_line"}:
            rectangle(doc)
        if name == "rectangle_polyline":
            msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
        elif name == "open_chain":
            msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)])
        elif name == "duplicate_reverse":
            msp.add_line((40, 0), (0, 0))
        elif name == "unsupported_arc":
            msp.add_arc((60, 0), radius=5, start_angle=0, end_angle=90)
        elif name == "bulged_polyline":
            msp.add_lwpolyline([(0, 0, 0.5), (40, 0, 0), (40, 20, 0), (0, 20, 0)], format="xyb", close=True)
        elif name == "block_insert":
            doc.blocks.new("PART").add_line((0, 0), (10, 0))
            msp.add_blockref("PART", (60, 0))
        elif name == "tolerance_gap":
            list(msp)[-1].dxf.end = (0.5e-6, 0, 0)
        elif name == "self_crossing":
            msp.add_lwpolyline([(0, 0), (40, 20), (0, 20), (40, 0)], close=True)
        elif name == "non_xy_line":
            msp.add_line((60, 0, 1e-12), (70, 0, 1e-12))
        elif name == "intersecting_rectangles":
            rectangle(doc)
            msp.add_lwpolyline([(20, -10), (60, -10), (60, 10), (20, 10)], close=True)
        elif name == "interior_endpoint_contact":
            rectangle(doc)
            msp.add_lwpolyline([(20, 0), (30, 10), (10, 10)], close=True)
        elif name == "collinear_overlap":
            msp.add_line((0, 0), (40, 0))
            msp.add_line((20, 0), (60, 0))
        elif name == "parallel_disjoint":
            msp.add_line((0, 0), (40, 0))
            msp.add_line((0, 1e-12), (40, 1e-12))
        doc.saveas(ROOT / "fixtures" / f"{name}.dxf")
    print(f"Generated {len(names)} synthetic fixtures. These are not factory-validated drawings.")


if __name__ == "__main__":
    generate()
