import random
import time

import redis

r = redis.Redis(port=6388, decode_responses=True)
keys = [k for k in r.keys("*")]
print(len(keys), keys[:3])


def meas(ks, n=1500):
    t = []
    for _ in range(n):
        k = random.choice(ks)
        s = time.perf_counter()
        r.execute_command("GRAPH.RO_QUERY", k, "MATCH (f:Fact {id: 'f0001'}) RETURN f.value")
        t.append((time.perf_counter() - s) * 1000)
    t.sort()
    return round(t[len(t) // 2], 3), round(t[int(len(t) * 0.99)], 3)


def ping(n=1500):
    t = []
    for _ in range(n):
        s = time.perf_counter()
        r.ping()
        t.append((time.perf_counter() - s) * 1000)
    t.sort()
    return round(t[len(t) // 2], 3)


gk = sorted(k for k in keys if k.startswith("plexus_t_g"))
print(len(gk))
print("N=200 q1 p50/p99", meas(gk), "ping", ping())
print("N=1   q1 (only first key)", meas(gk[:1]), "(same server, 199 other tenants present)")
for k in gk[1:]:
    r.execute_command("GRAPH.DELETE", k)
print("after delete, N=1 q1", meas(gk[:1]), "ping", ping())
print("N=200 again impossible; re-measure N=1", meas(gk[:1]))
