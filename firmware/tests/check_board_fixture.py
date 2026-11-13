#!/usr/bin/env python3
"""Check the saved fixture by connectivity, without the production LED formula."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
netlist = ET.parse(root / "fab/reference/card-netlist.xml").getroot()
nets = {}
for net in netlist.findall("./nets/net"):
    for node in net.findall("node"):
        key = (node.attrib["ref"], node.attrib["pin"])
        assert key not in nets, key
        nets[key] = net

# Physical VQFN-20 pins independently mapped to actual port bits.
gpio = {"20": 1, "1": 2, "2": 3, "5": 4, "6": 5}
cp = {}
for i in range(5):
    resistor = f"R{i + 1}"
    led_net = nets[(resistor, "2")]
    assert led_net.attrib["name"] == f"/CP{i}"
    mcu = [n for n in nets[(resistor, "1")].findall("node") if n.attrib["ref"] == "U2"]
    assert len(mcu) == 1
    pin = mcu[0].attrib["pin"]
    bit = gpio[pin]
    assert mcu[0].attrib["pinfunction"] == f"PA{bit}_{pin}"
    cp[led_net.attrib["name"]] = (i, 1 << bit)

fixture = (root / "firmware/tests/fixtures/card_led_pairs.h").read_text()
rows = [tuple(int(x, 0) for x in row) for row in re.findall(
    r"\{(\d+),(\d+),(0x[0-9a-f]+),(0x[0-9a-f]+)\}", fixture)]
assert len(rows) == 20
for i, row in enumerate(rows, 1):
    anode, high = cp[nets[(f"D{i}", "2")].attrib["name"]]
    cathode, low = cp[nets[(f"D{i}", "1")].attrib["name"]]
    assert row == (anode, cathode, high | low, high), (i, row)
assert len({row[:2] for row in rows}) == 20
print("board fixture: all 20 polarities and resistor/GPIO paths verified")
