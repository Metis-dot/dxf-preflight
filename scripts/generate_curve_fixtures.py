"""Generate four original curve-measurement examples without changing old fixtures."""

from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parents[1]


def generate():
    for name in ('curve_measurements', 'curve_wrapped_arc', 'curve_rejected_ocs', 'curve_equal_angles'):
        doc = ezdxf.new('R2010')
        doc.units = 4
        msp = doc.modelspace()
        if name == 'curve_measurements':
            msp.add_lwpolyline([(0, 0), (40, 0), (40, 20), (0, 20)], close=True)
            msp.add_circle((60, 5), 3, dxfattribs={'layer': 'ETCH', 'color': 1})
            msp.add_arc((60, 15), 4, 45, 135, dxfattribs={'layer': 'ETCH'})
        elif name == 'curve_wrapped_arc':
            msp.add_arc((10, 20), 5, 315, 45)
        elif name == 'curve_rejected_ocs':
            msp.add_circle((10, 20), 5, dxfattribs={'extrusion': (0, 0, -1)})
        else:
            msp.add_arc((10, 20), 5, 0, 360)
        doc.saveas(ROOT / 'fixtures' / f'{name}.dxf')
    print('Generated four original synthetic curve examples. All remain incomplete/manual-review-required.')


if __name__ == '__main__':
    generate()
