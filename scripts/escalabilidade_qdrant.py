"""
Concorrência: Qdrant | L2 ou Cosseno

Usa a coleção disk_test_<metrica> (m=16, ef_construction=200, ef_search=64).
A carga é gerada por N processos independentes (1 a 32), cada um com a sua
ligação ao motor. Em cada réplica o contentor é reiniciado e aquecido com 5 000
vetores da base; cada nível tem mais 500 consultas de aquecimento antes das
10 000 medidas. 3 réplicas; regista QPS, p50, p95, p99, repetições e falhas.

As consultas são pedidos HTTP diretos à API REST (o mesmo endpoint que o
qdrant-client usa): com o qdrant-client 1.9.2 o débito ficava limitado pelo
próprio cliente (ver diagnostico_concorrencia.py).

Os clientes correm na mesma máquina e partilham os 4 núcleos com o servidor.

Uso: python escalabilidade_qdrant.py --metric l2
"""
import argparse
import csv
import multiprocessing as mp
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import requests

# --- Protocolo comum (se mudar algo aqui, mudar também nos outros dois scripts) ---
QUERIES_FILE  = "sift/sift_query.npy"
BASE_FILE     = "sift/subsets/sift_base_1000000.npy"
NUM_QUERIES   = 10_000
WARMUP_N      = 5_000
PROCESSOS     = [1, 2, 4, 8, 16, 24, 32]      # número de processos cliente em paralelo
REPLICAS      = 3
EF_SEARCH     = 64
SEED          = 42
CHUNK         = 8                               # consultas enviadas de cada vez a cada processo
WARMUP_NIVEL  = 500                             # aquecimento antes de cada nível, com os mesmos processos


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
    while time.perf_counter() - t0 < timeout:
        try:
            if esperar_pronto():
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"{container} não ficou pronto após o reinício.")


def _arranque(_):
    """Tarefa curta usada só para pôr todos os processos a funcionar antes de medir."""
    time.sleep(0.2)
    return 1


def _tarefa(q):
    """Uma consulta. Se falhar a ligação, tenta outra vez (até 3) com uma ligação nova.
    Devolve (latência em ms ou None, repetições)."""
    t0 = time.perf_counter()
    rep = 0
    for tentativa in range(4):
        try:
            consultar(q)
            return (time.perf_counter() - t0) * 1000, rep
        except Exception:
            if tentativa == 3:
                return None, rep
            rep += 1
            recuperar()


def medir_nivel(queries, n_processos, aquecer=None):
    """Corre as consultas com n_processos em paralelo, cada um com a sua ligação,
    depois do aquecimento (se houver) com os mesmos processos.
    Devolve QPS, latências, repetições e falhas."""
    ctx = mp.get_context("fork")
    with ProcessPoolExecutor(max_workers=n_processos, mp_context=ctx, initializer=ligar) as ex:
        list(ex.map(_arranque, range(2 * n_processos)))          # todos os processos ligados
        if aquecer:
            list(ex.map(_tarefa, aquecer, chunksize=CHUNK))      # aquecimento deste nível
        t0 = time.perf_counter()
        res = list(ex.map(_tarefa, queries, chunksize=CHUNK))
        total = time.perf_counter() - t0
    lat = np.array([x for x, _ in res if x is not None])
    return len(lat) / total, lat, sum(r for _, r in res), sum(1 for x, _ in res if x is None)


def executar(motor, metric, container, esperar_pronto):
    queries, warmup = carregar_consultas(metric)
    csv_file = f"resultados_concorrencia_{motor.lower()}_{metric}.csv"
    with open(csv_file, "w", newline="") as f:
        csv.writer(f).writerow(["Replica", "Processos", "QPS", "p50_ms", "p95_ms", "p99_ms",
                                "Repeticoes", "Falhas"])
    for r in range(1, REPLICAS + 1):
        reiniciar(container, esperar_pronto)
        print(f"\n[{motor} {metric}] réplica {r}: aquecimento ({WARMUP_N} vetores)...", flush=True)
        medir_nivel(warmup, 4)
        for n in PROCESSOS:
            qps, lat, rep, fal = medir_nivel(queries, n, warmup[:WARMUP_NIVEL])
            p50, p95, p99 = np.percentile(lat, [50, 95, 99])
            aviso = (f" | {rep} repetidas" if rep else "") + (f" | {fal} FALHADAS" if fal else "")
            print(f"  {n:2d} processos: {qps:7.1f} QPS | p50 {p50:6.2f} ms | p95 {p95:6.2f} ms{aviso}", flush=True)
            with open(csv_file, "a", newline="") as f:
                csv.writer(f).writerow([r, n, round(qps, 2), round(p50, 4), round(p95, 4), round(p99, 4), rep, fal])
    print(f"\nFeito -> {csv_file}")
# ---


p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
metric = p.parse_args().metric
COLLECTION = f"disk_test_{metric}"
URL = f"http://localhost:6333/collections/{COLLECTION}"
_sessao = None


def ligar():
    """Executado em cada processo: cria a sua própria ligação HTTP."""
    global _sessao
    _sessao = requests.Session()


def recuperar():
    try:
        _sessao.close()
    except Exception:
        pass
    ligar()


def consultar(v):
    r = _sessao.post(f"{URL}/points/search", timeout=30,
                     json={"vector": v, "limit": 10, "params": {"hnsw_ef": EF_SEARCH}})
    r.raise_for_status()


def pronto():
    info = requests.get(URL, timeout=10).json()["result"]
    return (info["status"] == "green" and info["points_count"] == 1_000_000
            and (info.get("indexed_vectors_count") or 0) >= info["points_count"])


if not pronto():
    raise SystemExit(f"A coleção {COLLECTION} não existe, não tem 1M pontos ou não está indexada. "
                     f"Criar com: python ram_inserir_qdrant.py --metric {metric}")
executar("Qdrant", metric, "qdrant", pronto)
