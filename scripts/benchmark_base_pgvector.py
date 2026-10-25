"""
Benchmark de base: pgvector | L2 ou Cosseno

10 réplicas em 5 escalas (100 a 1M vetores), com 10 000 consultas por escala.
Em cada réplica o contentor é reiniciado. Para cada escala regista o tempo de
inserção, o tempo de construção do índice, o tempo total até a coleção estar
pronta, a RAM (pico na construção e média nas consultas, em relação ao repouso,
como no docker stats), as latências p50/p95/p99, o QPS e o Recall@10.

Uso: python benchmark_base_pgvector.py --metric l2
"""
import argparse
import csv
import os
import threading
import time

import docker
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_values

CONTAINER_NAME   = "pgvector"
BASE_DIR         = os.getcwd()   # pasta de onde se corre o script
SCALES           = [100, 1_000, 10_000, 100_000, 1_000_000]
REPLICATES       = 10
QUERY_FILE       = os.path.join(BASE_DIR, "sift/sift_query.npy")
WARMUP_QUERIES   = 50
INSERT_PAGE_SIZE = 1000

METRIC_CONFIG = {
    "l2":     {"hnsw_ops": "vector_l2_ops", "query_op": "<->", "gt_dir": os.path.join(BASE_DIR, "sift/gt"),
               "normalize": False, "results_file": os.path.join(BASE_DIR, "results_pgvector_l2.csv")},
    "cosine": {"hnsw_ops": "vector_cosine_ops", "query_op": "<=>", "gt_dir": os.path.join(BASE_DIR, "sift/gt_cosine"),
               "normalize": True, "results_file": os.path.join(BASE_DIR, "results_pgvector_cosine.csv")},
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


def ligar():
    conn = psycopg2.connect(host="127.0.0.1", port=5432, dbname="vectordb", user="postgres", password="postgres")
    register_vector(conn)
    return conn, conn.cursor()


def normalize(v):
    n = np.linalg.norm(v, axis=1, keepdims=True); n[n == 0] = 1
    return v / n


def calculate_recall(results, gt, k=10):
    return sum(len(set(results[i]) & set(gt[i][:k])) for i in range(len(results))) / (len(results) * k)


def run_bench(metric):
    cfg = METRIC_CONFIG[metric]
    conn, cur = ligar()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;"); conn.commit()
    query_vecs = np.load(QUERY_FILE).astype(np.float32)
    if cfg["normalize"]:
        query_vecs = normalize(query_vecs)
    sql = f"SELECT id FROM sift_bench ORDER BY embedding {cfg['query_op']} %s::vector LIMIT 10;"

    with open(cfg["results_file"], "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Replicate", "Scale", "Ingest_Time_s", "Index_Build_s", "Ready_Time_s",
                "RAM_Baseline_GB", "RAM_Build_Peak_GB", "RAM_Query_Avg_GB",
                "p50_ms", "p95_ms", "p99_ms", "QPS", "Recall@10"])
        for r in range(1, REPLICATES + 1):
            print(f"\n=== RÉPLICA {r} ===")
            cur.close(); conn.close()
            reiniciar_contentor(CONTAINER_NAME, lambda: ligar()[0].close() is None)
            conn, cur = ligar()
            for n in SCALES:
                vecs = np.load(os.path.join(BASE_DIR, f"sift/subsets/sift_base_{n}.npy")).astype(np.float32)
                gt = np.load(os.path.join(cfg["gt_dir"], f"gt_{n}.npy"))
                if cfg["normalize"]:
                    vecs = normalize(vecs)

                # apagar a tabela anterior antes de medir o repouso
                cur.execute("DROP TABLE IF EXISTS sift_bench;"); conn.commit()
                repouso = medir_repouso(CONTAINER_NAME)
                cur.execute("CREATE TABLE sift_bench (id SERIAL PRIMARY KEY, embedding vector(128));"); conn.commit()

                monitor = DockerMonitor(CONTAINER_NAME); monitor.start()
                t0 = time.perf_counter()
                execute_values(cur, "INSERT INTO sift_bench (embedding) VALUES %s",
                               [(v.tolist(),) for v in vecs], page_size=INSERT_PAGE_SIZE)
                conn.commit()
                t1 = time.perf_counter()
                cur.execute("SET maintenance_work_mem = '1GB';")
                cur.execute(f"CREATE INDEX ON sift_bench USING hnsw (embedding {cfg['hnsw_ops']}) "
                            f"WITH (m = 16, ef_construction = 200);")
                cur.execute("ANALYZE sift_bench;"); conn.commit()
                t2 = time.perf_counter()

                cur.execute("SET hnsw.ef_search = 64;")
                cur.execute("SET enable_seqscan = off;"); conn.commit()
                for q in query_vecs[:WARMUP_QUERIES]:
                    cur.execute(sql, (q.tolist(),)); cur.fetchall()
                monitor.fase = "consultas"
                lat, res = [], []
                for q in query_vecs:
                    ta = time.perf_counter()
                    cur.execute(sql, (q.tolist(),))
                    rows = cur.fetchall()
                    lat.append(time.perf_counter() - ta)
                    res.append([row[0] - 1 for row in rows])   # ids do PostgreSQL começam em 1
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
    cur.close(); conn.close()
    print("\nBenchmark concluído.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--metric", choices=["l2", "cosine"], required=True)
    run_bench(p.parse_args().metric)
