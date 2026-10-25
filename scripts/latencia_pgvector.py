"""
Latência detalhada: pgvector | L2 ou Cosseno

Usa a coleção disk_test_<metrica> (1M vetores, m=16, ef_search=64). Faz
REPLICAS execuções, cada uma com reinício do contentor, aquecimento com
WARMUP_N vetores da base (semente fixa) e as 10 000 consultas do SIFT1M em
sequência. O protocolo é o mesmo nos três scripts de latência: se mudar algum
valor da secção Protocolo comum, mudar também nos outros dois.

Antes de medir, confirma que o índice HNSW tem a classe de operadores da
métrica e que o planeador o usa.

Uso: python latencia_pgvector.py --metric l2
"""
import argparse
import csv
import subprocess
import time

import psycopg2
import numpy as np
from scipy.stats import kurtosis, skew

# --- Protocolo comum ---

QUERIES_FILE = "sift/sift_query.npy"
BASE_FILE = "sift/subsets/sift_base_1000000.npy"
NUM_QUERIES = 10_000
WARMUP_N = 5_000
REPLICAS = 5
EF_SEARCH = 64
SEED = 42
PERCENTIS = [10, 25, 50, 75, 90, 95, 99, 99.9]


def normalizar(x):
    n = np.linalg.norm(x, axis=1, keepdims=True)
    n[n == 0] = 1
    return x / n


def carregar_consultas(metric):
    """Consultas medidas e vetores de aquecimento (distintos das consultas)."""
    q = np.load(QUERIES_FILE)[:NUM_QUERIES].astype(np.float32)
    base = np.load(BASE_FILE, mmap_mode="r")
    idx = np.random.default_rng(SEED).choice(base.shape[0], WARMUP_N, replace=False)
    w = np.asarray(base[np.sort(idx)], dtype=np.float32)
    if metric == "cosine":
        q, w = normalizar(q), normalizar(w)
    return q.tolist(), w.tolist()


def reiniciar(container, esperar_pronto, timeout=600):
    subprocess.run(["docker", "restart", container], check=True, capture_output=True)
    t0 = time.perf_counter()
    while True:
        try:
            if esperar_pronto():
                return time.perf_counter() - t0
        except Exception:
            pass
        if time.perf_counter() - t0 > timeout:
            raise TimeoutError(f"{container} não ficou pronto após o reinício.")
        time.sleep(1)


def medir(consultar, queries, warmup, motor, metric, replica):
    print(f"[{motor} {metric}] réplica {replica}: aquecimento ({len(warmup)} vetores)...", flush=True)
    for w in warmup:
        consultar(w)
    print(f"[{motor} {metric}] réplica {replica}: a medir {len(queries)} consultas...", flush=True)
    lat = []
    for q in queries:
        t0 = time.perf_counter()
        consultar(q)
        lat.append((time.perf_counter() - t0) * 1000)
    return np.array(lat)


def guardar(motor, metric, resultados):
    """resultados: lista de arrays (uma por réplica)."""
    bruto = f"latencias_{motor.lower()}_{metric}.csv"
    resumo = f"latencias_{motor.lower()}_{metric}_resumo.csv"
    with open(bruto, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Replica", "Query_ID", "Latency_ms"])
        for r, lat in enumerate(resultados, start=1):
            for i, v in enumerate(lat, start=1):
                w.writerow([r, i, round(float(v), 4)])
    with open(resumo, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Motor", "Metrica", "Replica"] + [f"p{p}".replace(".", "_") for p in PERCENTIS]
                   + ["Max", "Skewness", "Kurtosis"])
        for r, lat in enumerate(resultados, start=1):
            p = np.percentile(lat, PERCENTIS)
            w.writerow([motor, metric, r] + [f"{x:.4f}" for x in p]
                       + [f"{lat.max():.4f}", f"{skew(lat):.4f}", f"{kurtosis(lat):.4f}"])
    print(f"\nFeito -> {bruto} e {resumo}")
    p50 = [np.percentile(l, 50) for l in resultados]
    p99 = [np.percentile(l, 99) for l in resultados]
    print(f"p50 por réplica: {', '.join(f'{x:.2f}' for x in p50)} ms")
    print(f"p99 por réplica: {', '.join(f'{x:.2f}' for x in p99)} ms")
# ---

p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
metric = p.parse_args().metric
TABLE = f"disk_test_{metric}"
OP, OPS = ("<->", "vector_l2_ops") if metric == "l2" else ("<=>", "vector_cosine_ops")
SQL = f"SELECT id FROM {TABLE} ORDER BY embedding {OP} %s::vector LIMIT 10;"
queries, warmup = carregar_consultas(metric)
estado = {}


def ligar():
    conn = psycopg2.connect(host="localhost", port=5432, user="postgres",
                            password="postgres", dbname="vectordb")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(f"SET hnsw.ef_search = {EF_SEARCH};")
    return conn, cur


def pronto():
    conn, cur = ligar()
    estado["conn"], estado["cur"] = conn, cur
    return True


def consultar(v):
    estado["cur"].execute(SQL, (v,))
    estado["cur"].fetchall()


# Verificações prévias
conn, cur = ligar()
cur.execute("SELECT count(*) FROM " + TABLE + ";")
if cur.fetchone()[0] != 1_000_000:
    raise SystemExit(f"A tabela {TABLE} não tem 1 000 000 de linhas.")
cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = %s AND indexdef ILIKE '%%hnsw%%';", (TABLE,))
defs = [r[0] for r in cur.fetchall()]
if not any(OPS in d for d in defs):
    raise SystemExit(f"Não existe índice HNSW com {OPS} em {TABLE}: {defs}")
cur.execute("EXPLAIN " + SQL, (queries[0],))
plano = " ".join(r[0] for r in cur.fetchall())
if "Index Scan" not in plano:
    raise SystemExit(f"O planeador não usa o índice HNSW:\n{plano}")
print(f"Índice verificado ({OPS}) e usado pelo planeador.")
conn.close()

resultados = []
for r in range(1, REPLICAS + 1):
    if "conn" in estado:
        estado["conn"].close()
    t = reiniciar("pgvector", pronto)
    print(f"[pgvector {metric}] réplica {r}: contentor pronto após {t:.0f} s", flush=True)
    resultados.append(medir(consultar, queries, warmup, "pgvector", metric, r))
estado["conn"].close()
guardar("pgvector", metric, resultados)
