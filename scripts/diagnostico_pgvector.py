"""
Tempo no servidor vs. latência no cliente: pgvector.

Para cada uma das 10 000 consultas mede a latência de uma consulta normal no
cliente e o tempo de planeamento e execução no PostgreSQL, com
EXPLAIN (ANALYZE, TIMING OFF). Mesmo protocolo da latência detalhada (tabela
disk_test_<metrica>, ef_search = 64, reinício e aquecimento com 5 000 vetores).

Uso: python diagnostico_pgvector.py --metric l2
"""
import argparse
import csv
import json
import subprocess
import time

import numpy as np
import psycopg2

p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
metric = p.parse_args().metric
TABLE = f"disk_test_{metric}"
OP = "<->" if metric == "l2" else "<=>"
SQL = f"SELECT id FROM {TABLE} ORDER BY embedding {OP} %s::vector LIMIT 10;"
CSV_FILE = f"diagnostico_pgvector_{metric}.csv"


def normalizar(x):
    n = np.linalg.norm(x, axis=1, keepdims=True); n[n == 0] = 1
    return x / n


def ligar():
    conn = psycopg2.connect(dbname="vectordb", user="postgres", password="postgres", host="localhost",
                            options="-c hnsw.ef_search=64")
    conn.autocommit = True
    return conn


queries = np.load("sift/sift_query.npy")[:10_000].astype(np.float32)
base = np.load("sift/subsets/sift_base_1000000.npy", mmap_mode="r")
idx = np.random.default_rng(42).choice(base.shape[0], 5_000, replace=False)
warmup = np.asarray(base[np.sort(idx)], dtype=np.float32)
if metric == "cosine":
    queries, warmup = normalizar(queries), normalizar(warmup)

subprocess.run(["docker", "restart", "pgvector"], check=True, capture_output=True)
for _ in range(120):
    try:
        conn = ligar(); break
    except Exception:
        time.sleep(1)
cur = conn.cursor()

# confirmar que o plano usa o índice HNSW
cur.execute("EXPLAIN " + SQL, (queries[0].tolist(),))
plano = " ".join(r[0] for r in cur.fetchall())
if "Index Scan" not in plano:
    raise SystemExit("O planeador não usa o índice HNSW.")

print(f"[pgvector {metric}] aquecimento (5 000 vetores)...", flush=True)
for v in warmup:
    cur.execute(SQL, (v.tolist(),)); cur.fetchall()

linhas = []
print(f"[pgvector {metric}] 10 000 consultas (cliente + EXPLAIN ANALYZE)...", flush=True)
for i, v in enumerate(queries):
    q = v.tolist()
    t0 = time.perf_counter()
    cur.execute(SQL, (q,)); cur.fetchall()
    cliente = (time.perf_counter() - t0) * 1000
    cur.execute("EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) " + SQL, (q,))
    plano = cur.fetchone()[0]
    plano = plano[0] if isinstance(plano, list) else json.loads(plano)[0]
    linhas.append((i, round(cliente, 4), round(plano["Planning Time"], 4), round(plano["Execution Time"], 4)))
conn.close()

with open(CSV_FILE, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Consulta", "Cliente_ms", "Planeamento_ms", "Execucao_ms"]); w.writerows(linhas)

a = np.array([l[1:] for l in linhas])
cli, pla, exe = np.median(a[:, 0]), np.median(a[:, 1]), np.median(a[:, 2])
srv = np.median(a[:, 1] + a[:, 2])
print(f"\nMedianas: cliente {cli:.2f} ms | servidor {srv:.2f} ms (planeamento {pla:.2f} + execução {exe:.2f})")
print(f"O servidor representa {100 * srv / cli:.0f}% da latência medida no cliente.")
print(f"Feito -> {CSV_FILE}")
