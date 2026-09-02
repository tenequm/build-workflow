#!/usr/bin/env python3
"""agy-session.py <conversation.db> [name]: per-step timeline and totals from an Antigravity CLI conversation DB (protobuf decoded with protoc --decode_raw)."""
import sys, sqlite3, subprocess, re, json
def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    db = argv[0]; name = argv[1] if len(argv) > 1 else db
    return _run(db, name, "--steps" in argv)


def _run(db, name, show_steps):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    def raw(blob):
        if not blob: return ''
        return subprocess.run(['protoc', '--decode_raw'], input=blob, capture_output=True).stdout.decode('utf8', 'replace')
    def ts(block):
        m = re.match(r'\s*(\d+) \{\s*1: (\d+)\s*2: (\d+)\s*\}', block)
        return int(m.group(2)) + int(m.group(3))/1e9 if m else None
    rows = con.execute('SELECT idx, step_type, status, metadata, step_payload FROM steps ORDER BY idx').fetchall()
    steps = []
    for idx, st, status, meta, payload in rows:
        d = raw(meta)
        # top-level blocks "N {\n  1: sec\n  2: nanos\n}"
        tsm = {int(k): int(s)+int(n)/1e9 for k, s, n in re.findall(r'^(\d+) \{\n  1: (\d+)\n  2: (\d+)\n\}', d, re.M)}
        usage = re.search(r'^9 \{\n((?:  .*\n)+?)\}', d, re.M)
        u = {}
        if usage:
            for k, v in re.findall(r'^  (\d+): (\d+)$', usage.group(1), re.M): u[int(k)] = int(v)
        steps.append(dict(idx=idx, type=st, status=status, created=tsm.get(1), started=tsm.get(6), ended=tsm.get(7) or tsm.get(8), usage=u, payload_len=len(payload or b'')))
    gm = con.execute('SELECT data FROM gen_metadata ORDER BY idx DESC LIMIT 1').fetchone()
    ctx = None
    if gm:
        g = raw(gm[0]); m = re.search(r'10 \{\n\s*1: (\d+)\n\s*4: (\d+)', g)
        if m: ctx = (int(m.group(1)), int(m.group(2)))
    first = min(s['created'] for s in steps if s['created']); last = max((s['ended'] or s['created'] or 0) for s in steps)
    by_type = {}
    for s in steps: by_type[s['type']] = by_type.get(s['type'], 0) + 1
    print(json.dumps(dict(name=name, steps=len(steps), by_type=by_type, first=first, last=last, span_s=round(last-first), context=ctx, last_usage=steps[-1]['usage'] if steps else None), indent=None))
    if show_steps:
        for s in steps: print(s['idx'], s['type'], round((s['created'] or 0)-first, 1), round(((s['ended'] or s['created'] or 0)-(s['started'] or s['created'] or 0)), 1), s['usage'], s['payload_len'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
