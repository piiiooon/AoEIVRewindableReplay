"""How much each recorded element adds to a dump log (owner 2026-11-12: "track how much of a recorded element bloats the
recorded file"; one reference replay, AgeIV_Replay_259818624, recorded again after each dump change).

    python tools/log_size.py logs/<name>.recorded.log [logs/<older>.recorded.log]

Per record type (A4D|<tag>|): bytes, share, lines; the game's own lines and warnings.log's line prefixes; per E-record field
(id, bp, x, z, ...) and how many E records repeat the same entity's previous record unchanged (what a delta format would
drop). With a second log: the per-type change. Bytes per game minute so logs of different lengths compare.
"""
import collections
import re
import sys

E_FIELDS = ["id", "bp", "x", "z", "vismask", "kind", "idle", "squad", "hp", "flags", "build", "queue", "target"]
P_TIME = re.compile(rb"A4D\|P\|([0-9.]+)\|")


def measure(path):
    tags, lines = collections.Counter(), collections.Counter()
    other = prefix = total = 0
    fields, erecs, esame, last = collections.Counter(), 0, 0, {}
    tmax = 0.0
    with open(path, "rb") as fh:
        for line in fh:
            total += len(line)
            i = line.find(b"A4D|")
            if i < 0:
                other += len(line)
                continue
            prefix += i
            j = line.find(b"|", i + 4)
            tag = line[i + 4:j if j > 0 else None].decode("ascii", "replace").strip()
            tags[tag] += len(line) - i
            lines[tag] += 1
            if tag == "P":
                m = P_TIME.match(line, i)
                if m:
                    tmax = max(tmax, float(m.group(1)))
            elif tag == "E":
                parts = line[i:].rstrip(b"\r\n").split(b"|", 4)
                if len(parts) < 5:
                    continue
                for r in parts[4].split(b";"):
                    f = r.split(b",")
                    erecs += 1
                    for k, v in zip(E_FIELDS, f):
                        fields[k] += len(v) + 1
                    if last.get(f[0]) == r:
                        esame += 1
                    last[f[0]] = r
    return {"total": total, "other": other, "prefix": prefix, "tags": tags, "lines": lines, "fields": fields,
            "erecs": erecs, "esame": esame, "minutes": tmax / 60.0}


def mb(b):
    return f"{b / 1e6:7.2f} MB"


def report(m, ref=None):
    mins = m["minutes"] or 1.0
    print(f"total {mb(m['total'])} over {m['minutes']:.1f} game minutes ({m['total'] / mins / 1e6:.2f} MB / min)")
    print(f"  game's own lines {mb(m['other'])}, warnings.log prefixes on A4D lines {mb(m['prefix'])}")
    print(f"\n{'tag':8} {'size':>10} {'share':>6} {'lines':>8} {'KB/min':>8}" + ("   vs older (KB/min)" if ref else ""))
    rmins = (ref or {}).get("minutes") or 1.0
    keys = sorted(set(m["tags"]) | set((ref or {}).get("tags", {})), key=lambda k: -m["tags"].get(k, 0))
    for k in keys:
        b = m["tags"].get(k, 0)
        if b < 1000 and not (ref and ref["tags"].get(k)):
            continue
        row = f"{k:8} {mb(b)} {100 * b / m['total']:5.1f}% {m['lines'].get(k, 0):8} {b / mins / 1e3:8.1f}"
        if ref:
            rb = ref["tags"].get(k, 0) / rmins / 1e3
            row += f"   {rb:8.1f} -> {b / mins / 1e3:8.1f}" + ("  (new)" if not ref["tags"].get(k) else "")
        print(row)
    if m["erecs"]:
        tot = sum(m["fields"].values())
        print(f"\nE records: {m['erecs']}, {tot / m['erecs']:.0f} bytes each; unchanged from the same entity's previous "
              f"record: {100 * m['esame'] / m['erecs']:.0f} %")
        for k in E_FIELDS:
            print(f"  {k:8} {mb(m['fields'][k])} {100 * m['fields'][k] / tot:5.1f}%")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    m = measure(sys.argv[1])
    ref = measure(sys.argv[2]) if len(sys.argv) > 2 else None
    report(m, ref)


if __name__ == "__main__":
    main()
