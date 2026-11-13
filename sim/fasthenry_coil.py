#!/usr/bin/env python3
"""FastHenry model of the ID-1 coil from scripts/gen_antenna.py's spiral (KiCad Python).

  fasthenry_coil.py [--inset MM] [--track MM] [--pitch MM] [--fasthenry BIN] [--work DIR]

Defaults are option A (NFC_Antenna_Rect_ID1_4turn_W090). Every spiral segment becomes a
35 um x track copper bar, split into filaments that resolve the 17.7 um skin depth at
13.56 MHz, and FastHenry solves it at 1 kHz (low-frequency L) and 13.56 MHz. Prints L and
R at both, and f0 with the NT3H2111's 44 / 50 / 56 pF.
"""
import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gen_antenna  # noqa: E402

CU_MM = 0.035
SIGMA_PER_MM = 5.8e4          # copper, S/mm
DEFAULT_BIN = Path.home() / "tools/FastHenry2/bin/fasthenry"


def deck(pts, track, nwinc, nhinc, freq):
    lines = [f"* ID-1 coil, {len(pts) - 1} segments, {track} mm x {CU_MM} mm", ".units mm",
             f".default sigma={SIGMA_PER_MM} z=0"]
    lines += [f"N{i} x={x:.4f} y={y:.4f}" for i, (x, y) in enumerate(pts)]
    lines += [f"E{i} N{i} N{i + 1} w={track} h={CU_MM} nwinc={nwinc} nhinc={nhinc} rw=2 rh=2"
              for i in range(len(pts) - 1)]
    lines += [f".external N0 N{len(pts) - 1}",
              f".freq fmin={freq} fmax={freq} ndec=1", ".end", ""]
    return "\n".join(lines)


def solve(text, binary, work):
    work.mkdir(parents=True, exist_ok=True)
    (work / "coil.inp").write_text(text)
    subprocess.run([str(binary), "coil.inp"], cwd=work, check=True, capture_output=True)
    out = []
    for m in re.finditer(r"Impedance matrix for frequency = ([\d.eE+-]+) 1 x 1\s+([-\d.eE+]+)\s+([-\d.eE+]+)j",
                         (work / "Zc.mat").read_text()):
        f, r, x = (float(v) for v in m.groups())
        out.append((f, r, x / (2 * math.pi * f)))
    return out


def main():
    inset, track, pitch, _ = gen_antenna.DESIGNS["NFC_Antenna_Rect_ID1_4turn_W090"]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inset", type=float, default=inset, help="outer turn centreline inset, mm")
    ap.add_argument("--track", type=float, default=track)
    ap.add_argument("--pitch", type=float, default=pitch)
    ap.add_argument("--nwinc", type=int, default=9)
    ap.add_argument("--nhinc", type=int, default=3)
    ap.add_argument("--fasthenry", default=str(DEFAULT_BIN))
    ap.add_argument("--work", default="build/fasthenry")
    args = ap.parse_args()
    _, _, _, end_offset = gen_antenna.DESIGNS["NFC_Antenna_Rect_ID1_4turn_W090"]
    pts = gen_antenna.spiral(args.inset, args.pitch, end_offset)
    # FastHenry keeps only the last .freq card, so each frequency is its own solve
    res = [r for f in (1e3, 13.56e6)
           for r in solve(deck(pts, args.track, args.nwinc, args.nhinc, f), args.fasthenry, Path(args.work))]
    print(f"inset {args.inset} track {args.track} pitch {args.pitch} (gap {args.pitch - args.track:.2f}), "
          f"outer edge {args.inset - args.track / 2:.2f} mm, inner edge "
          f"{args.inset + (gen_antenna.TURNS - 1) * args.pitch + args.track / 2:.2f} mm")
    for f, r, l in res:
        f0 = " ".join(f"{1 / (2 * math.pi * math.sqrt(l * c * 1e-12)) / 1e6:.2f}" for c in (44, 50, 56))
        print(f"  {f / 1e6:9.4f} MHz  L {l * 1e6:.4f} uH  R {r:.3f} ohm  f0 @44/50/56 pF {f0} MHz")
    return 0


if __name__ == "__main__":
    sys.exit(main())
