#!/usr/bin/env python3
"""Build the two-card panel and export it for JLC (gerbers, drill, merged BOM/CPL).

Usage: scripts/export-panel.py   (after both cards pass scripts/check.sh)

Parts are read from the panel itself: every footprint with an LCSC number that
is not a fiducial, tooling hole or mouse bite (those are excluded from BOM and
position files) and is not one of the cards' unfitted parts (C1, L1, TP1-TP3,
now C101/C201 and so on). Rotations get the same JLC offsets as single cards.
"""
import ast
import csv
import hashlib
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
CLI = shutil.which('kicad-cli') or '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
KPY = '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3'
OUT = ROOT / 'fab/panel-v2'
BOARD = OUT / 'panel.kicad_pcb'
UNFITTED = {'C1', 'L1', 'TP1', 'TP2', 'TP3'}
ASSEMBLED = 2 * 36

# The same rotation table the single-card export uses (a literal dict in export-card.py).
JLC_ROTATION = ast.literal_eval(re.search(r"JLC_ROTATION = (\{.*?\})", (ROOT / 'scripts/export-card.py').read_text()).group(1))


def run(*args):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True)


def original(ref):
    """D201 -> D1: the reference on the card the part came from."""
    m = re.match(r'([A-Z]+)(\d+)$', ref)
    return f'{m.group(1)}{int(m.group(2)) % 100}' if m else ref


run(KPY, ROOT / 'scripts/build_panel.py')
gerbers = OUT / 'gerbers'
if gerbers.exists():
    shutil.rmtree(gerbers)
gerbers.mkdir()
run(CLI, 'pcb', 'export', 'gerbers', '-l', 'F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts', '-o', str(gerbers) + '/', BOARD)
run(CLI, 'pcb', 'export', 'drill', '-o', str(gerbers) + '/', BOARD)
run(CLI, 'pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'front', '-o', OUT / 'positions-kicad.csv', BOARD)

# Footprint fields straight from the board file (the panel has no schematic).
text = BOARD.read_text()
parts = {}
for m in re.finditer(r'\n\t\(footprint "([^"]+)"(.*?)(?=\n\t\(footprint |\n\t\((?:segment|via|gr_|arc|zone|group|embedded)|\Z)', text, re.S):
    fpid, body = m.group(1), m.group(2)
    props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', body))
    ref = props.get('Reference', '')
    if not props.get('LCSC') or original(ref) in UNFITTED:
        continue
    parts[ref] = (props.get('Value', ''), fpid, props['LCSC'])
assert len(parts) == ASSEMBLED, (len(parts), sorted(parts))

groups = defaultdict(list)
for ref, key in parts.items():
    groups[key].append(ref)
with (OUT / 'bom.csv').open('w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for (value, footprint, lcsc), refs in sorted(groups.items()):
        w.writerow([value, ','.join(sorted(refs)), footprint, lcsc])

placed = set()
with (OUT / 'positions-kicad.csv').open(newline='') as source, (OUT / 'cpl.csv').open('w', newline='') as target:
    w = csv.writer(target)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for row in csv.DictReader(source):
        ref = row['Ref']
        if ref not in parts:
            continue
        rot = (float(row['Rot']) + JLC_ROTATION.get(parts[ref][2], 0)) % 360
        w.writerow([ref, row['PosX'] + 'mm', row['PosY'] + 'mm', 'Top', f'{rot:.6f}'])
        placed.add(ref)
assert placed == set(parts), set(parts) ^ placed

with ZipFile(OUT / 'panel-v2-gerbers.zip', 'w', ZIP_DEFLATED) as z:
    for file in sorted(gerbers.iterdir()):
        if file.is_file():
            z.write(file, file.name)
run(CLI, 'pcb', 'render', '--side', 'top', '--width', '1800', '--height', '800', '-o', OUT / 'panel-top.png', BOARD)
with (OUT / 'SHA256SUMS').open('w') as f:
    for file in [BOARD, OUT / 'panel-v2-gerbers.zip', OUT / 'bom.csv', OUT / 'cpl.csv']:
        f.write(hashlib.sha256(file.read_bytes()).hexdigest() + '  ' + str(file.relative_to(ROOT)) + '\n')
print(f'Exported {len(parts)} assembled parts on the two-card panel: {OUT}')
