"""
Diagnóstico das opções de protocolo do ensaio de concorrência.

Compara quatro formas de gerar a carga, nas mesmas condições:
  1. Qdrant com o qdrant-client, em processos;
  2. Qdrant com pedidos HTTP diretos, em processos;
  3. ChromaDB com a biblioteca chromadb, em threads;
  4. ChromaDB com a biblioteca chromadb, em processos.

Métrica L2, coleção disk_test_l2, 1 a 16 clientes, 5 000 consultas por nível
(com aquecimento de 500), uma réplica. O contentor é reiniciado antes de cada modo.
Uma consulta que falhe é repetida até 3 vezes com uma ligação nova.

Saída: diagnostico_concorrencia.csv
Uso:   python diagnostico_concorrencia.py
"""
import csv
import multiprocessing as mp
import subprocess
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import chromadb
import numpy as np
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import SearchParams

COLLECTION = "disk_test_l2"
QDRANT_URL = f"http://localhost:6333/collections/{COLLECTION}"
NIVEIS = [1, 2, 4, 8, 16]
NUM_QUERIES = 5_000
WARMUP_N = 500
EF_SEARCH = 64
CHUNK = 8
CSV_FILE = "diagnostico_concorrencia.csv"

QUERIES = np.load("sift/sift_query.npy")[:NUM_QUERIES].astype(np.float32).tolist()
_base = np.load("sift/subsets/sift_base_1000000.npy", mmap_mode="r")
_idx = np.random.default_rng(42).choice(_base.shape[0], WARMUP_N, replace=False)
WARMUP = np.asarray(_base[np.sort(_idx)], dtype=np.float32).tolist()


def criar(cliente):
    if cliente == "qdrant-client":
        return QdrantClient(host="localhost", port=6333, timeout=120)
    if cliente == "http":
        return requests.Session()
    return chromadb.HttpClient(host="localhost", port=8000).get_collection(COLLECTION)


def consultar(cliente, c, v):
    if cliente == "qdrant-client":
        c.search(collection_name=COLLECTION, query_vector=v, limit=10,
                 search_params=SearchParams(hnsw_ef=EF_SEARCH))
    elif cliente == "http":
        r = c.post(f"{QDRANT_URL}/points/search", timeout=30,
                   json={"vector": v, "limit": 10, "params": {"hnsw_ef": EF_SEARCH}})
        r.raise_for_status()
    else:
        c.query(query_embeddings=[v], n_results=10)


def com_repeticoes(cliente, obter, renovar, v):
    """Devolve (latência em ms ou None se falhou, número de repetições)."""
    t0 = time.perf_counter()
    for tentativa in range(4):
        try:
            consultar(cliente, obter(), v)
            return (time.perf_counter() - t0) * 1000, tentativa
        except Exception:
            if tentativa == 3:
                return None, 3
            renovar()


# carga gerada por processos
_cliente, _c = None, None


def _iniciar(cliente):
    global _cliente, _c
    _cliente, _c = cliente, criar(cliente)


def _renovar_proc():
    global _c
    _c = criar(_cliente)


def _tarefa_proc(v):
    return com_repeticoes(_cliente, lambda: _c, _renovar_proc, v)


def _arranque(_):
    time.sleep(0.2)


def nivel_processos(cliente, n):
    with ProcessPoolExecutor(max_workers=n, mp_context=mp.get_context("fork"),
                             initializer=_iniciar, initargs=(cliente,)) as ex:
        list(ex.map(_arranque, range(2 * n)))
        list(ex.map(_tarefa_proc, WARMUP, chunksize=CHUNK))
        t0 = time.perf_counter()
        res = list(ex.map(_tarefa_proc, QUERIES, chunksize=CHUNK))
        return res, time.perf_counter() - t0


# carga gerada por threads (um cliente por thread)
def nivel_threads(cliente, n):
    loc = threading.local()

    def obter():
        if not hasattr(loc, "c"):
            loc.c = criar(cliente)
        return loc.c

    def renovar():
        loc.c = criar(cliente)

    def tarefa(v):
        return com_repeticoes(cliente, obter, renovar, v)

    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(tarefa, WARMUP))
        t0 = time.perf_counter()
        res = list(ex.map(tarefa, QUERIES))
        return res, time.perf_counter() - t0


def reiniciar(container, pronto, timeout=600):
    subprocess.run(["docker", "restart", container], check=True, capture_output=True)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        try:
            if pronto():
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"{container} não ficou pronto.")


def qdrant_pronto():
    info = requests.get(QDRANT_URL, timeout=10).json()["result"]
    return info["status"] == "green" and info["points_count"] == 1_000_000


def chroma_pronto():
    c = chromadb.HttpClient(host="localhost", port=8000)
    c.heartbeat()
    return c.get_collection(COLLECTION).count() == 1_000_000


MODOS = [("Qdrant", "qdrant-client", "processos", "qdrant", qdrant_pronto),
         ("Qdrant", "http", "processos", "qdrant", qdrant_pronto),
         ("ChromaDB", "chromadb", "threads", "chromadb", chroma_pronto),
         ("ChromaDB", "chromadb", "processos", "chromadb", chroma_pronto)]

with open(CSV_FILE, "w", newline="") as f:
    csv.writer(f).writerow(["Motor", "Cliente", "Geracao_carga", "Clientes", "QPS",
                            "p50_ms", "p95_ms", "Repeticoes", "Falhas", "Pct_repetidas", "Pct_falhadas"])

for motor, cliente, geracao, container, pronto in MODOS:
    reiniciar(container, pronto)
    print(f"\n== {motor} | {cliente} | {geracao}", flush=True)
    for n in NIVEIS:
        res, total = (nivel_processos if geracao == "processos" else nivel_threads)(cliente, n)
        lat = np.array([x for x, _ in res if x is not None])
        rep = sum(r for _, r in res)
        fal = sum(1 for x, _ in res if x is None)
        consultas_rep = sum(1 for _, r in res if r > 0)
        qps = len(lat) / total
        p50, p95 = (np.percentile(lat, [50, 95]) if len(lat) else (float("nan"), float("nan")))
        pct_rep, pct_fal = 100 * consultas_rep / len(res), 100 * fal / len(res)
        print(f"  {n:2d} clientes: {qps:7.1f} QPS | p50 {p50:6.2f} ms | p95 {p95:6.2f} ms | "
              f"repetidas {pct_rep:5.1f}% | falhadas {pct_fal:5.1f}%", flush=True)
        with open(CSV_FILE, "a", newline="") as f:
            csv.writer(f).writerow([motor, cliente, geracao, n, round(qps, 2), round(p50, 4), round(p95, 4),
                                    rep, fal, round(pct_rep, 2), round(pct_fal, 2)])

print(f"\nFeito -> {CSV_FILE}")
