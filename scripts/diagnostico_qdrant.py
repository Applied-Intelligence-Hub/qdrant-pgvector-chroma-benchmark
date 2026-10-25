"""
Diagnóstico da latência bimodal do Qdrant.

Para cada consulta regista o tempo medido no cliente (pedido HTTP completo) e o
tempo de pesquisa que o próprio Qdrant devolve (campo "time"). Se as consultas
lentas também forem lentas no servidor, o tempo a mais está na pesquisa; se não,
está na comunicação. Usa pedidos HTTP diretos e o protocolo do latencia_qdrant.py.

Uso: python diagnostico_qdrant.py --metric l2
"""
import argparse
import csv
import subprocess
import time

import numpy as np
import requests

p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
METRIC = p.parse_args().metric
COLLECTION = f"disk_test_{METRIC}"
CSV_FILE = f"diagnostico_qdrant_{METRIC}.csv"
URL = f"http://localhost:6333/collections/{COLLECTION}/points/search"
QUERIES_FILE = "sift/sift_query.npy"
BASE_FILE = "sift/subsets/sift_base_1000000.npy"
REPLICAS, WARMUP_N, EF_SEARCH, SEED = 5, 5_000, 64, 42

queries = np.load(QUERIES_FILE)[:10_000].astype(np.float32).tolist()
base = np.load(BASE_FILE, mmap_mode="r")
idx = np.random.default_rng(SEED).choice(base.shape[0], WARMUP_N, replace=False)
warmup = np.asarray(base[np.sort(idx)], dtype=np.float32)
queries = np.array(queries, dtype=np.float32)
if METRIC == "cosine":
    def normalizar(x):
        n = np.linalg.norm(x, axis=1, keepdims=True); n[n == 0] = 1
        return x / n
    queries, warmup = normalizar(queries), normalizar(warmup)
queries, warmup = queries.tolist(), warmup.tolist()


def pesquisar(sessao, v):
    t0 = time.perf_counter()
    r = sessao.post(URL, json={"vector": v, "limit": 10, "params": {"hnsw_ef": EF_SEARCH}})
    cliente = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    return cliente, r.json()["time"] * 1000


def esperar_pronto():
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 600:
        try:
            info = requests.get(f"http://localhost:6333/collections/{COLLECTION}").json()["result"]
            if info["status"] == "green" and info["points_count"] == 1_000_000:
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError("O Qdrant não ficou pronto.")


with open(CSV_FILE, "w", newline="") as f:
    csv.writer(f).writerow(["Replica", "Query_ID", "Cliente_ms", "Servidor_ms"])

for rep in range(1, REPLICAS + 1):
    subprocess.run(["docker", "restart", "qdrant"], check=True, capture_output=True)
    esperar_pronto()
    sessao = requests.Session()
    print(f"réplica {rep}: aquecimento...", flush=True)
    for w in warmup:
        pesquisar(sessao, w)
    print(f"réplica {rep}: a medir...", flush=True)
    res = [pesquisar(sessao, q) for q in queries]
    sessao.close()
    cli = np.array([x[0] for x in res]); srv = np.array([x[1] for x in res])
    print(f"  cliente  p50={np.percentile(cli, 50):.2f} ms  p95={np.percentile(cli, 95):.2f} ms  (>3 ms: {np.mean(cli > 3) * 100:.1f}%)")
    print(f"  servidor p50={np.percentile(srv, 50):.2f} ms  p95={np.percentile(srv, 95):.2f} ms", flush=True)
    with open(CSV_FILE, "a", newline="") as f:
        w = csv.writer(f)
        for i, (c, s) in enumerate(res, start=1):
            w.writerow([rep, i, round(c, 4), round(s, 4)])

print(f"\nFeito -> {CSV_FILE}")
