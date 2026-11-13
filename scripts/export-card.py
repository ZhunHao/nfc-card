#!/usr/bin/env python3
"""Export one checked card design and a matched JLCPCB BOM/CPL pair.

Usage: scripts/export-card.py <board> [--contact FILE]
  <board>         a directory under hardware/, e.g. terminal
  --contact FILE  rebuild a private copy of the board with the phone number from
                  FILE (see contact.example.json) under build/personal/ and export
                  that instead. The committed board is not modified.

Output goes to fab/<board>-v2/ (gitignored).
"""
import argparse
import csv
import os
import hashlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
CLI = shutil.which('kicad-cli') or '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
KICAD_PYTHON = os.environ.get('KICAD_PYTHON', '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3')
ap = argparse.ArgumentParser(description='Export a JLCPCB fab package for one card.')
ap.add_argument('board')
ap.add_argument('--contact', type=Path, help='private contact JSON (adds the phone line)')
ARGS = ap.parse_args()
NAME = ARGS.board
BOARD = ROOT / f'hardware/{NAME}/{NAME}.kicad_pcb'
SCH = BOARD.with_suffix('.kicad_sch')
REV = 'v2'  # rev B: QFN U2, D21, soft-start (Q1/R7/R8/C4), antenna option A
OUT = ROOT / f'fab/{NAME}-{REV}'
EXCLUDED = {'C1', 'L1', 'TP1', 'TP2', 'TP3'}
ASSEMBLED = 36
# JLC's library orients these parts differently from KiCad's footprints. Checked
# 2026-10-28 in JLCONE's placement viewer on the Terminal card: U2's pin-1 dot sat
# on pin 6's position (needs 90 degrees clockwise) and Q1's on pad 3's side (180).
# Added to KiCad's rotation (counter-clockwise positive, as in the CPL).
JLC_ROTATION = {'C507118': -90, 'C155329': 180}

def run(*args):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True)

run(ROOT / 'scripts/check.sh')
if ARGS.contact:
    private = ROOT / f'build/personal/{NAME}.kicad_pcb'
    private.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([KICAD_PYTHON, str(ROOT / f'hardware/{NAME}/build_{NAME}.py'), str(private)],
                   cwd=ROOT, check=True, env={**os.environ, 'CARD_CONTACT': str(ARGS.contact.resolve())})
    BOARD = private
OUT.mkdir(parents=True, exist_ok=True)
gerbers = OUT / 'gerbers'
gerbers.mkdir(exist_ok=True)
run(CLI, 'pcb', 'export', 'gerbers', '-l', 'F.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,F.Paste,B.Paste,Edge.Cuts', '-o', str(gerbers)+'/', BOARD)
run(CLI, 'pcb', 'export', 'drill', '-o', str(gerbers)+'/', BOARD)
run(CLI, 'pcb', 'export', 'pos', '--format', 'csv', '--units', 'mm', '--side', 'front', '-o', OUT / 'positions-kicad.csv', BOARD)
run(CLI, 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o', OUT / 'netlist.xml', SCH)

groups = defaultdict(list)
populated = set()
lcsc_of = {}
for comp in ET.parse(OUT / 'netlist.xml').findall('./components/comp'):
    ref = comp.attrib['ref']
    if ref in EXCLUDED:
        continue
    fields = {f.attrib['name']: f.text for f in comp.findall('./fields/field')}
    lcsc = fields.get('LCSC')
    if not lcsc:
        raise ValueError(f'Missing LCSC number: {ref}')
    groups[(comp.findtext('value'), comp.findtext('footprint'), lcsc)].append(ref)
    populated.add(ref)
    lcsc_of[ref] = lcsc
assert len(populated) == ASSEMBLED, populated

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
        if ref not in populated:
            continue
        assert row['Side'].lower() in ('top', 'front'), row
        rot = (float(row['Rot']) + JLC_ROTATION.get(lcsc_of[ref], 0)) % 360
        w.writerow([ref, row['PosX']+'mm', row['PosY']+'mm', 'Top', f'{rot:.6f}'])
        placed.add(ref)
assert placed == populated, (placed, populated)

with ZipFile(OUT / f'{NAME}-{REV}-gerbers.zip', 'w', ZIP_DEFLATED) as z:
    for file in sorted(gerbers.iterdir()):
        if file.is_file():
            z.write(file, file.name)
for side in ('top', 'bottom'):
    run(CLI, 'pcb', 'render', '--side', side, '--width', '1500', '--height', '1000', '-o', OUT / f'{NAME}-{side}.png', BOARD)
with (OUT / 'SHA256SUMS').open('w') as f:
    for file in [BOARD, SCH, OUT / f'{NAME}-{REV}-gerbers.zip', OUT / 'bom.csv', OUT / 'cpl.csv']:
        f.write(hashlib.sha256(file.read_bytes()).hexdigest()+'  '+str(file.relative_to(ROOT))+'\n')
print(f'Exported {len(populated)} assembled parts per board, matching BOM and CPL: {OUT}')
