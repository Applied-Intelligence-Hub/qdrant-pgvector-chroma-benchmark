"""
Benchmark de base: Qdrant | L2 ou Cosseno

10 réplicas em 5 escalas (100 a 1M vetores), com 10 000 consultas por escala.
Em cada réplica o contentor é reiniciado. Para cada escala regista o tempo de
inserção, o tempo de construção do índice, o tempo total até a coleção estar
pronta, a RAM (pico na construção e média nas consultas, em relação ao repouso,
como no docker stats), as latências p50/p95/p99, o QPS e o Recall@10.

A indexação fica desligada durante o upload (indexing_threshold = 0) e é ligada
no fim com 1 KB, para o HNSW ser construído em todas as escalas. Com o valor por
omissão (20 000 KB), o Qdrant faz pesquisa exaustiva até aos 100 000 vetores.

Uso: python benchmark_base_qdrant.py --metric l2
"""
import argparse
import csv
import threading
import time

import docker
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (CollectionStatus, Distance, HnswConfigDiff,
                                  OptimizersConfigDiff, SearchParams, VectorParams)

CONTAINER_NAME = "qdrant"
SCALES         = [100, 1_000, 10_000, 100_000, 1_000_000]
REPLICATES     = 10
QUERY_FILE     = "sift/sift_query.npy"
WARMUP_QUERIES = 50
TIMEOUT_S      = 1800

METRIC_CONFIG = {
    "l2":     {"distance": Distance.EUCLID, "gt_dir": "sift/gt", "normalize": False,
               "results_file": "results_qdrant_l2.csv"},
    "cosine": {"distance": Distance.COSINE, "gt_dir": "sift/gt_cosine", "normalize": True,
               "results_file": "results_qdrant_cosine.csv"},
}

# --- Memória (igual nos três scripts) ---
# Mesmo valor do docker stats (usage - inactive_file), separado em construção e consultas.
def ram_gb(container) -> float:
    ms = container.stats(stream=False)["memory_stats"]
    return (ms["usage"] - ms.get("stats", {}).get("inactive_file", 0)) / (1024 ** 3)


def medir_repouso(container_name: str, pausa_s: float = 5.0, amostras: int = 5) -> float:
    time.sleep(pausa_s)
    cont = docker.from_env().containers.get(container_name)
    leituras = []
    for _ in range(amostras):
        leituras.append(ram_gb(cont))
        time.sleep(0.5)
    return float(np.median(leituras))


class DockerMonitor(threading.Thread):
    """Amostra a memória a cada 0,5 s, guardando a fase em que cada leitura foi feita."""
    def __init__(self, container_name):
        super().__init__()
        self.container = docker.from_env().containers.get(container_name)
        self.amostras = []          # (fase, GB)
        self.fase = "construcao"
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            try:
                self.amostras.append((self.fase, ram_gb(self.container)))
                time.sleep(0.5)
            except Exception:
                break

    def stop(self):
        self.stop_flag = True

    def resultados(self, repouso):
        constr = [v for f, v in self.amostras if f == "construcao"] or [repouso]
        consul = [v for f, v in self.amostras if f == "consultas"] or [repouso]
        return max(constr) - repouso, float(np.mean(consul)) - repouso
# ---


def reiniciar_contentor(container_name: str, esperar_pronto, timeout_s: int = 600) -> None:
    """Reinicia o contentor e espera que o serviço volte a responder."""
    docker.from_env().containers.get(container_name).restart()
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        try:
            if esperar_pronto():
                return
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"O contentor {container_name} não ficou pronto após o reinício.")


def normalize(v):
    n = np.linalg.norm(v, axis=1, keepdims=True); n[n == 0] = 1
    return v / n


def calculate_recall(results, gt, k=10):
    return sum(len(set(results[i]) & set(gt[i][:k])) for i in range(len(results))) / (len(results) * k)


def esperar_indexacao(client, n):
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < TIMEOUT_S:
        info = client.get_collection("sift_bench")
        if info.status == CollectionStatus.GREY:
            client.update_collection("sift_bench", optimizer_config=OptimizersConfigDiff())
        if (info.status == CollectionStatus.GREEN and (info.points_count or 0) == n
                and (info.indexed_vectors_count or 0) >= n):
            return
        time.sleep(0.2)
    raise TimeoutError("A indexação não terminou dentro do limite.")


def run_bench(metric):
    cfg = METRIC_CONFIG[metric]
    client = QdrantClient(host="localhost", port=6333, timeout=300)
    query_vecs = np.load(QUERY_FILE).astype(np.float32)
    if cfg["normalize"]:
        query_vecs = normalize(query_vecs)

    with open(cfg["results_file"], "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Replicate", "Scale", "Ingest_Time_s", "Index_Build_s", "Ready_Time_s",
                "RAM_Baseline_GB", "RAM_Build_Peak_GB", "RAM_Query_Avg_GB",
                "p50_ms", "p95_ms", "p99_ms", "QPS", "Recall@10"])
        for r in range(1, REPLICATES + 1):
            print(f"\n=== RÉPLICA {r} ===")
            reiniciar_contentor(CONTAINER_NAME, lambda: client.get_collections() is not None)
            for n in SCALES:
                vecs = np.load(f"sift/subsets/sift_base_{n}.npy").astype(np.float32)
                gt = np.load(f"{cfg['gt_dir']}/gt_{n}.npy")
                if cfg["normalize"]:
                    vecs = normalize(vecs)

                # apagar a coleção anterior antes de medir o repouso
                if client.collection_exists("sift_bench"):
                    client.delete_collection("sift_bench")
                repouso = medir_repouso(CONTAINER_NAME)

                client.create_collection(
                    collection_name="sift_bench",
                    vectors_config=VectorParams(size=128, distance=cfg["distance"]),
                    hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
                    optimizers_config=OptimizersConfigDiff(indexing_threshold=0))

                monitor = DockerMonitor(CONTAINER_NAME); monitor.start()
                t0 = time.perf_counter()
                client.upload_collection("sift_bench", vectors=vecs, ids=list(range(n)), batch_size=1000)
                t1 = time.perf_counter()
                client.update_collection("sift_bench",
                                         optimizer_config=OptimizersConfigDiff(indexing_threshold=1))
                esperar_indexacao(client, n)
                t2 = time.perf_counter()

                for q in query_vecs[:WARMUP_QUERIES]:
                    client.search("sift_bench", query_vector=q, limit=10,
                                  search_params=SearchParams(hnsw_ef=64))
                monitor.fase = "consultas"
                lat, res = [], []
                for q in query_vecs:
                    ta = time.perf_counter()
                    hits = client.search("sift_bench", query_vector=q, limit=10,
                                         search_params=SearchParams(hnsw_ef=64))
                    lat.append(time.perf_counter() - ta)
                    res.append([int(h.id) for h in hits])
                monitor.stop(); monitor.join()

                pico, media = monitor.resultados(repouso)
                lat_ms = np.array(lat) * 1000
                p50, p95, p99 = np.percentile(lat_ms, [50, 95, 99])
                qps = len(query_vecs) / np.sum(lat)
                rec = calculate_recall(res, gt)
                writer.writerow([r, n, f"{t1-t0:.4f}", f"{t2-t1:.4f}", f"{t2-t0:.4f}",
                                 f"{repouso:.4f}", f"{pico:.4f}", f"{media:.4f}",
                                 f"{p50:.4f}", f"{p95:.4f}", f"{p99:.4f}", f"{qps:.2f}", f"{rec:.4f}"])
                f.flush()
                print(f"  N={n}: ingestão {t1-t0:.1f}s + índice {t2-t1:.1f}s | p50={p50:.2f}ms "
                      f"QPS={qps:.0f} Recall={rec:.4f} | RAM pico +{pico:.2f} GB, consultas +{media:.2f} GB")
    print("\nBenchmark concluído.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--metric", choices=["l2", "cosine"], required=True)
    run_bench(p.parse_args().metric)
