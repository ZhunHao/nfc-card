#!/usr/bin/env python3
"""Fail unless a board's schematic netlist matches the shared NTUAS reference.

Both personal cards must keep the NTUAS circuit exactly: same parts, values,
footprints, LCSC numbers and connectivity. Only placement, routing and artwork
may differ. Usage: check_netlist.py <exported-netlist.xml>
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "fab/reference/card-netlist.xml"

def summary(path):
    root = ET.parse(path).getroot()
    parts = {}
    for comp in root.findall("./components/comp"):
        fields = {f.attrib["name"]: f.text for f in comp.findall("./fields/field")}
        parts[comp.attrib["ref"]] = (comp.findtext("value"), comp.findtext("footprint"), fields.get("LCSC"))
    nets = {frozenset((n.attrib["ref"], n.attrib["pin"]) for n in net.findall("node"))
            for net in root.findall("./nets/net")}
    return parts, nets

ref_parts, ref_nets = summary(REFERENCE)
parts, nets = summary(sys.argv[1])
problems = []
for r in sorted(set(ref_parts) | set(parts)):
    if ref_parts.get(r) != parts.get(r):
        problems.append(f"{r}: reference {ref_parts.get(r)} vs board {parts.get(r)}")
if nets != ref_nets:
    problems.append(f"connectivity differs ({len(ref_nets ^ nets)} nets not shared)")
if problems:
    print("\n".join(problems))
    sys.exit(1)
