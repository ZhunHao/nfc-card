"""Board thickness for both cards, set by the build scripts (KiCad 10 Python).

pcbnew's Python bindings set the board thickness but don't expose the stackup, so the
saved file still lists the old FR4 core and the gerber job file would describe a 1.0 mm
board. `save` therefore rewrites the one core thickness in the saved stackup so the
layers add up to THICKNESS_MM. scripts/check.sh checks both values.
"""
import re

import pcbnew

THICKNESS_MM = 0.8   # bank-card thickness (ISO/IEC 7810 ID-1 is 0.76 mm); JLC tolerance ±0.1 mm

CORE = re.compile(r'(\(layer "dielectric 1"\s*\(type "core"\)\s*\(thickness )([0-9.]+)\)')


def save(board, path):
    board.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(THICKNESS_MM))
    board.Save(str(path))
    text = path.read_text()
    stackup = re.search(r'\(stackup.*?\(copper_finish', text, re.S).group(0)
    layers = sum(float(t) for t in re.findall(r'\(thickness ([0-9.]+)\)', stackup))
    old = float(CORE.search(stackup).group(2))
    core = round(THICKNESS_MM - (layers - old), 4)
    text, n = CORE.subn(lambda m: f'{m.group(1)}{core:g})', text)
    assert n == 1, f'expected one FR4 core in {path}, found {n}'
    path.write_text(text)
