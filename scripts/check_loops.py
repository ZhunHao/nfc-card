#!/usr/bin/env python3
"""Closed copper loops inside the coil (read-only). Run with KiCad 10's bundled Python.

  check_loops.py BOARD.kicad_pcb [--max-supply-mm2 100]

The card has no ground plane, so any closed loop inside the antenna is a shorted turn
that absorbs the phone's field and detunes the coil. Three kinds are reported:

  net loops     a cycle of tracks, vias and pads within one net. Any enclosed area fails.
  supply loops  every pair of shunt paths across the supply (C2, C3, C4, U1 VOUT-VSS, U2
                VCC-GND) joined by the shortest copper, with JP1 and Q1 (bypassed, as it
                is while the card runs) in series. Caps are near-shorts at 13.56 MHz.
                Fails above --max-supply-mm2.
  LED loops     the drive loop of each Charlieplexed LED while lit. Reported only: an off
                LED is open at RF, and a lit one has ~400 ohm in series.

Area is the shoelace area of the loop's track-centreline polygon. A component is drawn
as a straight line between its pad centres. The graph is trusted only if every routed
net comes out as one connected piece, which DRC also requires.
"""
import argparse
import heapq
import math
import sys

import pcbnew

MM = 1e6
NET_LOOP_MAX_MM2 = 0.01   # tracks overlapping where they meet a pad give zero-area cycles
SUPPLY_NETS = ("/VOUT", "/VCC", "/GND", "/SS_CAP")


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def mm(v):
    return (v.x / MM, v.y / MM)


def seg_dist(p, a, b):
    """Distance from p to segment ab, and the parameter t of the closest point."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.dist(p, (a[0] + t * dx, a[1] + t * dy)), t


def arc_points(a, m, b, n=24):
    (x1, y1), (x2, y2), (x3, y3) = a, m, b
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    cx = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    cy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    r = math.dist((cx, cy), a)
    t1, t2, t3 = (math.atan2(p[1] - cy, p[0] - cx) for p in (a, m, b))
    sweep = (t3 - t1) % (2 * math.pi)
    if (t2 - t1) % (2 * math.pi) > sweep:
        sweep -= 2 * math.pi
    return [(cx + r * math.cos(t1 + sweep * i / n), cy + r * math.sin(t1 + sweep * i / n)) for i in range(n + 1)]


def area(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


class Copper:
    """Board copper as a graph: nodes are pads, vias and track junctions, edges are tracks."""

    def __init__(self, board):
        self.pads, self.vias, tracks = {}, [], []
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname():
                    self.pads[(fp.GetReference(), p.GetNumber())] = p
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                self.vias.append((t.GetNetname(), mm(t.GetPosition()), t.GetWidth(pcbnew.F_Cu) / 2 / MM))
            else:
                a, b = mm(t.GetStart()), mm(t.GetEnd())
                pts = arc_points(a, mm(t.GetMid()), b) if t.GetClass() == "PCB_ARC" else [a, b]
                tracks.append(dict(net=t.GetNetname(), layer=t.GetLayer(), w=t.GetWidth() / MM, pts=pts))
        self.dsu = DSU()
        self.edges = []
        self._build([piece for t in tracks for piece in self._split(t, tracks)])

    def _pad_hit(self, pad, pt, layer):
        return pad.IsOnLayer(layer) and pad.HitTest(pcbnew.VECTOR2I(int(pt[0] * MM), int(pt[1] * MM)))

    def _split(self, t, tracks):
        """Cut a track wherever a via, another track's end or a pad joins its interior."""
        pts, n = t["pts"], len(t["pts"]) - 1
        cuts = set()

        def interior(i, s):
            return 1e-6 < i + s < n - 1e-6

        for net, c, r in self.vias:
            if net == t["net"]:
                for i in range(n):
                    d, s = seg_dist(c, pts[i], pts[i + 1])
                    if d < r + t["w"] / 2 and interior(i, s):
                        cuts.add(round(i + s, 6))
        for o in tracks:
            if o is t or o["net"] != t["net"] or o["layer"] != t["layer"]:
                continue
            for end in (o["pts"][0], o["pts"][-1]):
                if min(math.dist(end, pts[0]), math.dist(end, pts[-1])) <= t["w"] / 2:
                    continue
                for i in range(n):
                    d, s = seg_dist(end, pts[i], pts[i + 1])
                    if d < t["w"] / 2 and interior(i, s):
                        cuts.add(round(i + s, 6))
        for (ref, _), pad in self.pads.items():
            if ref == "L1" or pad.GetNetname() != t["net"]:
                continue
            if self._pad_hit(pad, pts[0], t["layer"]) or self._pad_hit(pad, pts[-1], t["layer"]):
                continue
            for i in range(n):
                hit = next((k / 20 for k in range(1, 20) if self._pad_hit(pad, self._at(pts, i + k / 20), t["layer"])), None)
                if hit is not None:
                    cuts.add(round(i + hit, 6))
                    break
        xs = [0] + sorted(cuts) + [n]
        for a, b in zip(xs, xs[1:]):
            yield dict(t, pts=[self._at(pts, a)] + [pts[i] for i in range(len(pts)) if a < i < b] + [self._at(pts, b)])

    @staticmethod
    def _at(pts, x):
        i = min(int(x), len(pts) - 2)
        s = x - i
        return (pts[i][0] + s * (pts[i + 1][0] - pts[i][0]), pts[i][1] + s * (pts[i + 1][1] - pts[i][1]))

    def _build(self, pieces):
        ends = []
        for k, pc in enumerate(pieces):
            for side in (0, -1):
                key, pt = ("end", k, side), pc["pts"][side]
                ends.append((key, pt, pc))
                for vi, (net, c, r) in enumerate(self.vias):
                    if net == pc["net"] and math.dist(pt, c) < r + pc["w"] / 2:
                        self.dsu.union(key, ("via", vi))
                for pid, pad in self.pads.items():
                    if pad.GetNetname() == pc["net"] and self._pad_hit(pad, pt, pc["layer"]):
                        self.dsu.union(key, ("pad",) + pid)
        for i, (ka, pa, ca) in enumerate(ends):
            for kb, pb, cb in ends[i + 1:]:
                if ca["net"] == cb["net"] and ca["layer"] == cb["layer"] \
                        and math.dist(pa, pb) < max(ca["w"], cb["w"]) / 2:
                    self.dsu.union(ka, kb)
        for k, pc in enumerate(pieces):
            self.edges.append(dict(u=self.dsu.find(("end", k, 0)), v=self.dsu.find(("end", k, -1)), net=pc["net"],
                                   poly=pc["pts"], len=sum(math.dist(a, b) for a, b in zip(pc["pts"], pc["pts"][1:])),
                                   kind="track"))

    def node(self, ref, num):
        return self.dsu.find(("pad", ref, num))

    def pad_on(self, ref, net):
        return next(num for (r, num), p in self.pads.items() if r == ref and p.GetNetname() == net)

    def part(self, ref, a, b, kind=None):
        """A component as an edge between two of its pads."""
        pa, pb = mm(self.pads[(ref, a)].GetPosition()), mm(self.pads[(ref, b)].GetPosition())
        return dict(u=self.node(ref, a), v=self.node(ref, b), net=None, poly=[pa, pb], len=math.dist(pa, pb),
                    kind=kind or ref)

    def nets(self):
        return sorted({p.GetNetname() for p in self.pads.values()} - {""})

    def members(self, net):
        return {self.node(*pid) for pid, p in self.pads.items() if p.GetNetname() == net} | \
               {self.dsu.find(("via", i)) for i, v in enumerate(self.vias) if v[0] == net}


def adjacency(edges):
    adj = {}
    for i, e in enumerate(edges):
        adj.setdefault(e["u"], []).append((e["v"], i))
        adj.setdefault(e["v"], []).append((e["u"], i))
    return adj


def loop_through(edges, i):
    """Edge i closed by the shortest path between its ends that avoids it, or None."""
    adj, s, t = adjacency(edges), edges[i]["v"], edges[i]["u"]
    if s == t:
        return [(t, s, i)]
    dist, prev, pq = {s: 0}, {}, [(0, s)]
    while pq:
        d, x = heapq.heappop(pq)
        if x == t:
            break
        if d > dist[x]:
            continue
        for y, j in adj.get(x, []):
            if j != i and d + edges[j]["len"] + 1e-9 < dist.get(y, math.inf):
                dist[y], prev[y] = d + edges[j]["len"] + 1e-9, (x, j)
                heapq.heappush(pq, (dist[y], y))
    if t not in dist:
        return None
    path, x = [], t
    while x != s:
        x0, j = prev[x]
        path.append((x0, x, j))
        x = x0
    return [(t, s, i)] + path[::-1]


def measure(edges, cycle):
    pts = []
    for a, _, j in cycle:
        poly = edges[j]["poly"]
        pts += poly if edges[j]["u"] == a else poly[::-1]
    parts = sorted({edges[j]["kind"] for _, _, j in cycle} - {"track"})
    return area(pts), sum(edges[j]["len"] for _, _, j in cycle), parts


def net_loops(cu, net):
    """(components, largest single-net loop area) for one net."""
    edges = [e for e in cu.edges if e["net"] == net]
    dsu = DSU()
    for e in edges:
        dsu.union(e["u"], e["v"])
    components = len({dsu.find(m) for m in cu.members(net)})
    worst = 0.0
    for i in range(len(edges)):
        cycle = loop_through(edges, i)
        if cycle:
            worst = max(worst, measure(edges, cycle)[0])
    return components, worst


def supply_loops(cu):
    rails = [e for e in cu.edges if e["net"] in SUPPLY_NETS]
    rails += [cu.part("JP1", "1", "2"),
              cu.part("Q1", cu.pad_on("Q1", "/VCC"), cu.pad_on("Q1", "/SS_CAP"), "Q1(on)")]
    shunts = [cu.part("C2", "1", "2"), cu.part("C3", "1", "2"), cu.part("C4", "1", "2"),
              cu.part("U1", cu.pad_on("U1", "/VOUT"), cu.pad_on("U1", "/GND")),
              cu.part("U2", cu.pad_on("U2", "/VCC"), cu.pad_on("U2", "/GND"))]
    out = []
    for i, a in enumerate(shunts):
        for b in shunts[i + 1:]:
            edges = rails + [b, a]
            a_, perim, parts = measure(edges, loop_through(edges, len(edges) - 1))
            out.append((a_, perim, f"{a['kind']}-{b['kind']}", parts))
    return sorted(out, reverse=True)


def led_loops(cu, board):
    """Lit-LED loop: U2 PAi -> Ri -> CPi -> LED -> CPj -> Rj -> PAj, closed inside U2."""
    base = [e for e in cu.edges if e["net"].startswith(("/CP", "/PA"))]
    pa_of_cp = {}
    for r in ("R1", "R2", "R3", "R4", "R5"):
        n1, n2 = cu.pads[(r, "1")].GetNetname(), cu.pads[(r, "2")].GetNetname()
        base.append(cu.part(r, "1", "2"))
        cp, pa = (n1, n2) if n1.startswith("/CP") else (n2, n1)
        pa_of_cp[cp] = pa
    out = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref.startswith("D") or ref == "D21":
            continue
        pa_k, pa_a = (pa_of_cp[cu.pads[(ref, n)].GetNetname()] for n in ("1", "2"))
        edges = base + [cu.part(ref, "1", "2"), cu.part("U2", cu.pad_on("U2", pa_a), cu.pad_on("U2", pa_k))]
        a, perim, _ = measure(edges, loop_through(edges, len(edges) - 1))
        out.append((a, perim, ref))
    return sorted(out, reverse=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("board")
    ap.add_argument("--max-supply-mm2", type=float, default=100.0)
    args = ap.parse_args()
    board = pcbnew.LoadBoard(args.board)
    cu = Copper(board)
    problems = []

    worst_net = (0.0, "")
    for net in cu.nets():
        if net.startswith("unconnected") or not cu.members(net):
            continue
        components, worst = net_loops(cu, net)
        if components != 1:
            problems.append(f"{net}: copper graph has {components} pieces, so the loop search can't be trusted")
        if worst > NET_LOOP_MAX_MM2:
            problems.append(f"{net}: closed copper loop of {worst:.2f} mm²")
        worst_net = max(worst_net, (worst, net))

    supply = supply_loops(cu)
    for a, perim, name, parts in supply:
        print(f"  supply {name:7s} {a:6.1f} mm²  {perim:6.1f} mm  via {', '.join(parts)}")
        if a > args.max_supply_mm2:
            problems.append(f"supply loop {name} encloses {a:.1f} mm² (limit {args.max_supply_mm2:g})")
    leds = led_loops(cu, board)
    print(f"  LED loops (report only): largest {leds[0][2]} {leds[0][0]:.1f} mm², smallest {leds[-1][2]} {leds[-1][0]:.1f} mm²")
    print(f"  largest single-net loop: {worst_net[0]:.3f} mm²")

    for p in problems:
        print("  problem: " + p)
    a, _, name, _ = supply[0]
    print(f"worst supply loop {name} {a:.1f} mm² (limit {args.max_supply_mm2:g})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
