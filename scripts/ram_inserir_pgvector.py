"""
Insere 1M vetores no pgvector (coleção disk_test_<metrica>, m=16, ef_construction=200).

Usado com o monitorizar_ram.py para o perfil de RAM. A coleção fica criada para os
ensaios de latência, concorrência e arranque a frio.

Usa a base vectordb e maintenance_work_mem = 1GB, como o benchmark_base_pgvector.py. Os ids
começam em 1: para os outros ensaios, as tabelas são recriadas pelo disco_pgvector.py.

Uso: python ram_inserir_pgvector.py --metric l2
"""
import argparse
import time

import numpy as np
import psycopg2
from psycopg2.extras import execute_values

parser = argparse.ArgumentParser()
parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
args = parser.parse_args()

DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 1_000_000
BATCH_SIZE = 5000
MAINTENANCE_WORK_MEM = "1GB"   # igual ao benchmark_base_pgvector.py

if args.metric == "l2":
    TABLE_NAME, INDEX_OPS, NORMALIZE = "disk_test_l2", "vector_l2_ops", False
else:
    TABLE_NAME, INDEX_OPS, NORMALIZE = "disk_test_cosine", "vector_cosine_ops", True

conn = psycopg2.connect(dbname="vectordb", user="postgres", password="postgres",
                        host="localhost", port=5432)
conn.autocommit = True
cur = conn.cursor()

print(f"A recriar tabela '{TABLE_NAME}' no pgvector (base 'vectordb')...")
cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME};")
cur.execute(f"CREATE TABLE {TABLE_NAME} (id bigserial PRIMARY KEY, embedding vector(128));")

print("A carregar vetores...")
vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
if NORMALIZE:
    print("A normalizar vetores (Cosseno)...")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vectors = vectors / norms

print("A iniciar inserção em lotes...")
t0 = time.perf_counter()
for i in range(0, TOTAL_VECTORS, BATCH_SIZE):
    batch = vectors[i:i + BATCH_SIZE].tolist()
    values = [(f"[{','.join(map(str, v))}]",) for v in batch]
    execute_values(cur, f"INSERT INTO {TABLE_NAME} (embedding) VALUES %s", values)
    if (i + BATCH_SIZE) % 100_000 == 0:
        print(f"  {i + BATCH_SIZE} vetores inseridos...")
ingestao_s = time.perf_counter() - t0

print(f"A construir índice HNSW (maintenance_work_mem = {MAINTENANCE_WORK_MEM})...")
cur.execute(f"SET maintenance_work_mem = '{MAINTENANCE_WORK_MEM}';")
t1 = time.perf_counter()
cur.execute(f"""
    CREATE INDEX ON {TABLE_NAME} USING hnsw (embedding {INDEX_OPS})
    WITH (m = 16, ef_construction = 200);
""")
indice_s = time.perf_counter() - t1

print(f"\nConcluído. Ingestão: {ingestao_s:.0f} s | índice: {indice_s:.0f} s")
cur.close()
conn.close()
