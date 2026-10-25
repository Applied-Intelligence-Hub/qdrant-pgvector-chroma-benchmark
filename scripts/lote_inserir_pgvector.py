"""
Inserção em lote: pgvector | L2 ou Cosseno

Insere 100 000 vetores com lotes de 100 a 50 000 (3 réplicas por lote) e regista
a ingestão, a construção do índice e o tempo total até a coleção estar pronta.

Usa uma tabela própria (batch_test), com maintenance_work_mem = 1GB. O page_size
do execute_values é o tamanho do lote.

Uso: python lote_inserir_pgvector.py --metric l2
"""
import argparse, csv, gc, statistics, time
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 100_000
BATCH_SIZES = [100, 1_000, 10_000, 50_000]
REPLICAS = 3
TABLE = "batch_test"
M, EF_CONSTRUCTION = 16, 200
MAINTENANCE_WORK_MEM = "1GB"

CFG = {"l2": ("vector_l2_ops", False, "resultados_batch_pgvector_L2.csv", "L2"),
       "cosine": ("vector_cosine_ops", True, "resultados_batch_pgvector_Cosine.csv", "Cosine")}


def main(metric):
    ops, normalizar, csv_file, label = CFG[metric]
    vecs = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
    if normalizar:
        n = np.linalg.norm(vecs, axis=1, keepdims=True); n[n == 0] = 1; vecs = vecs / n
    linhas = [(v,) for v in vecs]

    conn = psycopg2.connect(dbname="vectordb", user="postgres", password="postgres", host="localhost")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    register_vector(conn)
    cur.execute(f"SET maintenance_work_mem = '{MAINTENANCE_WORK_MEM}';")

    with open(csv_file, "w", newline="") as f:
        csv.writer(f).writerow(["DB", "Metric", "Batch_Size", "Pedido_efetivo", "Replica",
                                "Ingestao_s", "Indexacao_s", "Total_s", "Throughput_vec_s"])

    for b_size in BATCH_SIZES:
        totais = []
        for rep in range(1, REPLICAS + 1):
            cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
            cur.execute(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, embedding vector(128));")
            print(f"[pgvector {label}] lote={b_size} rep={rep}: a correr...", flush=True)
            t0 = time.perf_counter()
            execute_values(cur, f"INSERT INTO {TABLE} (embedding) VALUES %s", linhas, page_size=b_size)
            t1 = time.perf_counter()
            cur.execute(f"CREATE INDEX ON {TABLE} USING hnsw (embedding {ops}) "
                        f"WITH (m = {M}, ef_construction = {EF_CONSTRUCTION});")
            t2 = time.perf_counter()
            ingest, index, total = t1 - t0, t2 - t1, t2 - t0
            totais.append(total)
            print(f"[pgvector {label}] lote={b_size} rep={rep}: ingestão {ingest:.2f}s + "
                  f"indexação {index:.2f}s = {total:.2f}s ({TOTAL_VECTORS/total:.0f} vec/s)")
            with open(csv_file, "a", newline="") as f:
                csv.writer(f).writerow(["pgvector", label, b_size, b_size, rep, round(ingest, 3),
                                        round(index, 3), round(total, 3),
                                        round(TOTAL_VECTORS / total, 1)])
            gc.collect()
        print(f"  mediana: {statistics.median(totais):.2f}s")
    cur.execute(f"DROP TABLE IF EXISTS {TABLE};")
    cur.close(); conn.close()
    print(f"\nFeito -> {csv_file}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
    main(p.parse_args().metric)
