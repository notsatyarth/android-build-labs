import csv, glob, statistics as st, sys, json
res = {}
for d in sorted(glob.glob('profiler-out/*-r[0-9]')):
    c = d.split('/')[-1].rsplit('-r',1)[0]
    rows = list(csv.reader(open(d + '/benchmark.csv')))
    scen, val = rows[0][1:], rows[3][1:]
    for r in rows[4:]:
        if not r[0].startswith('measured'): continue
        for i, v in enumerate(r[1:]):
            if v == '': continue
            res.setdefault(c, {}).setdefault((scen[i], val[i]), []).append(float(v)/1000)
out = {}
for c, m in res.items():
    for (s, v), xs in m.items():
        out.setdefault(c, {})[f'{s}|{v}'] = xs
        print(f'{c} {s:7} {v:20} n={len(xs):2} median={st.median(xs):6.2f} min={min(xs):6.2f} max={max(xs):6.2f}')
json.dump(out, open('profiler-out/agg.json','w'), indent=1)
