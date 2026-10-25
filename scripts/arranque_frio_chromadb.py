"""
Arranque a frio vs. cache quente: ChromaDB | L2 ou Cosseno

Usa a coleção disk_test_<metrica> (1M vetores). Em cada uma das 10 réplicas:
pára o contentor, limpa a page cache, volta a arrancá-lo e mede o tempo até o
motor e a coleção estarem disponíveis. Depois corre 1 000 consultas sem
aquecimento (fase a frio) e as mesmas 1 000 logo a seguir (fase quente).

Precisa de sudo sem palavra-passe para limpar a page cache (ver README).

Uso: python arranque_frio_chromadb.py --metric l2
"""
import argparse
import csv
import gc
import subprocess
import time

import docker
import numpy as np
import chromadb

# --- Protocolo comum (se mudar algo aqui, mudar também nos outros dois scripts) ---
QUERIES_FILE = "sift/sift_query.npy"
NUM_QUERIES  = 1_000
REPLICATES   = 10
EF_SEARCH    = 64
TIMEOUT_S    = 600

GT_FILE = {"l2": "sift/gt/gt_1000000.npy", "cosine": "sift/gt_cosine/gt_1000000.npy"}
HEADERS = ["Replicate", "DB", "Metric", "Arranque_s",
           "First_Resp_Cold_ms", "Cold_First10_Mean_ms", "p50_Cold_ms", "p95_Cold_ms",
           "First_Resp_Warm_ms", "p50_Warm_ms", "p95_Warm_ms",
           "Recall_Cold", "Recall_Warm", "Excesso_Frio_s"]


def normalizar(v):
    n = np.linalg.norm(v, axis=1, keepdims=True)
    n[n == 0] = 1
    return v / n


def recall(resultados, gt, k=10):
    return 100 * sum(len(set(r) & set(g[:k])) for r, g in zip(resultados, gt)) / (len(resultados) * k)


def limpar_cache():
    """Limpa a page cache do sistema. Chamado com o contentor parado."""
    if subprocess.run(["sync"]).returncode != 0:
        raise RuntimeError("Falha no sync.")
    r = subprocess.run(["sudo", "sh", "-c", "echo 3 > /proc/sys/vm/drop_caches"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Falha ao limpar a page cache (verificar sudo NOPASSWD): {r.stderr.strip()}")
    time.sleep(1)


def arranque_a_frio(container, esperar_pronto):
    """Pára o contentor, limpa a cache com o contentor parado, arranca-o e espera
    que o motor e a coleção estejam disponíveis. Devolve o tempo de arranque (s)."""
    cont = docker.from_env().containers.get(container)
    if cont.status == "running":
        cont.stop()
    limpar_cache()
    t0 = time.perf_counter()
    cont.start()
    while time.perf_counter() - t0 < TIMEOUT_S:
        try:
            if esperar_pronto():
                return time.perf_counter() - t0
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError(f"{container} não ficou pronto.")


def fase(pesquisar, queries):
    """Executa as consultas em sequência; devolve latências (ms), resultados e tempo total (s)."""
    lat, res = [], []
    t_ini = time.perf_counter()
    for q in queries:
        t0 = time.perf_counter()
        res.append(pesquisar(q))
        lat.append((time.perf_counter() - t0) * 1000)
    return np.array(lat), res, time.perf_counter() - t_ini


def executar(motor, metric, container, esperar_pronto, preparar_ligacao, pesquisar):
    """A ligação é aberta antes da fase a frio (sem consultar o índice), para a primeira
    consulta não incluir o tempo de ligação."""
    queries = np.load(QUERIES_FILE)[:NUM_QUERIES].astype(np.float32)
    if metric == "cosine":
        queries = normalizar(queries)
    queries = queries.tolist()
    gt = np.load(GT_FILE[metric])[:NUM_QUERIES]
    label = "L2" if metric == "l2" else "Cosine"
    csv_file = f"resultados_cold_warm_{motor.lower()}_{label}.csv"
    with open(csv_file, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=HEADERS).writeheader()
    for r in range(1, REPLICATES + 1):
        arranque = arranque_a_frio(container, esperar_pronto)
        preparar_ligacao()
        frio, res_f, tot_f = fase(pesquisar, queries)
        quente, res_q, tot_q = fase(pesquisar, queries)
        linha = {"Replicate": r, "DB": motor, "Metric": label, "Arranque_s": round(arranque, 3),
                 "First_Resp_Cold_ms": round(frio[0], 4), "Cold_First10_Mean_ms": round(frio[:10].mean(), 4),
                 "p50_Cold_ms": round(np.percentile(frio, 50), 4), "p95_Cold_ms": round(np.percentile(frio, 95), 4),
                 "First_Resp_Warm_ms": round(quente[0], 4), "p50_Warm_ms": round(np.percentile(quente, 50), 4),
                 "p95_Warm_ms": round(np.percentile(quente, 95), 4),
                 "Recall_Cold": round(recall(res_f, gt), 2), "Recall_Warm": round(recall(res_q, gt), 2),
                 "Excesso_Frio_s": round(max(0.0, tot_f - tot_q), 4)}
        with open(csv_file, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writerow(linha)
        print(f"[{motor} {label}] réplica {r}: arranque {arranque:.1f}s | 1.ª resposta {frio[0]:.1f} ms | "
              f"p50 frio {linha['p50_Cold_ms']:.2f} / quente {linha['p50_Warm_ms']:.2f} ms | "
              f"recall {linha['Recall_Cold']:.1f}%", flush=True)
        gc.collect()
    print(f"\nFeito -> {csv_file}")
# ---


p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
metric = p.parse_args().metric
COLLECTION = f"disk_test_{metric}"
estado = {}


def pronto():
    client = chromadb.HttpClient(host="localhost", port=8000)
    client.heartbeat()
    client.get_collection(COLLECTION)
    return True


def preparar_ligacao():
    estado["col"] = chromadb.HttpClient(host="localhost", port=8000).get_collection(COLLECTION)   # sem pesquisar


def pesquisar(v):
    return [int(x) for x in estado["col"].query(query_embeddings=[v], n_results=10)["ids"][0]]


pronto()
col = chromadb.HttpClient(host="localhost", port=8000).get_collection(COLLECTION)
cfg = (getattr(col, "configuration", None) or {}).get("hnsw", {})
espaco = "l2" if metric == "l2" else "cosine"
if col.count() != 1_000_000 or cfg.get("ef_search") != EF_SEARCH or cfg.get("space") != espaco:
    raise SystemExit(f"Coleção {COLLECTION} inválida (count={col.count()}, hnsw={cfg}). "
                     f"Criar com: python ram_inserir_chromadb.py --metric {metric}")
executar("ChromaDB", metric, "chromadb", pronto, preparar_ligacao, pesquisar)
