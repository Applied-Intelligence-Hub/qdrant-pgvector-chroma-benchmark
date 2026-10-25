"""
Consumo de disco do pgvector (1M vetores, m=16, ef_construction=200).

O total é o pg_total_relation_size() da tabela (tabela, índice HNSW, chave
primária, mapas e TOAST). O WAL é registado à parte e fica fora do total,
porque pertence a todo o cluster.

Cria as tabelas disk_test_<metrica> com ids a começar em 0, que são as usadas
nos ensaios de latência, concorrência e arranque a frio.

Uso: python disco_pgvector.py --metric l2
"""
import argparse
import numpy as np
import psycopg2
import time
import csv
import subprocess
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

parser = argparse.ArgumentParser()
parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
args = parser.parse_args()

DATA_FILE          = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS      = 1_000_000
M_VALUE            = 16
EF_CONSTRUCTION    = 200
POSTGRES_CONTAINER = "pgvector"

if args.metric == "l2":
    TABLE_NAME = "disk_test_l2"
    INDEX_NAME = "hnsw_idx_l2"         
    HNSW_OPS   = "vector_l2_ops"
    NORMALIZE  = False
    CSV_FILE   = "disk_pgvector_l2.csv"
else:
    TABLE_NAME = "disk_test_cosine"
    INDEX_NAME = "hnsw_idx_cosine"     
    HNSW_OPS   = "vector_cosine_ops"
    NORMALIZE  = True
    CSV_FILE   = "disk_pgvector_cosine.csv"

def bytes_to_mb(value):
    return value / (1024 * 1024)

def get_pg_wal_mb(container_name):
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "du", "-sb", "/var/lib/postgresql/data/pg_wal"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return int(result.stdout.split()[0]) / (1024 * 1024)
    except:
        pass
    return 0.0

conn = psycopg2.connect(
    host="localhost", port=5432, user="postgres",
    password="postgres", dbname="vectordb"
)
conn.autocommit = True
cur = conn.cursor()
register_vector(conn)

vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)

if NORMALIZE:
    print("A normalizar vetores (Cosseno)...")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vectors = vectors / norms

print(f"Removendo tabela antiga '{TABLE_NAME}'...")
cur.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")

# Limpar também o índice órfão caso exista de um teste anterior
print(f"Removendo indice antigo '{INDEX_NAME}' se existir...")
cur.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")

print("Criando tabela...")
cur.execute(f"""
    CREATE TABLE {TABLE_NAME} (
        id BIGINT PRIMARY KEY,
        embedding vector(128)
    )
""")

print("Inserindo vetores (Bulk Loading com execute_values)...")
vector_tuples = [(i, v.tolist()) for i, v in enumerate(vectors)]
execute_values(
    cur,
    f"INSERT INTO {TABLE_NAME} (id, embedding) VALUES %s",
    vector_tuples,
    page_size=10000
)

print("\nCriando indice HNSW...")
cur.execute("SET maintenance_work_mem = '1GB';")
cur.execute(f"""
    CREATE INDEX {INDEX_NAME} ON {TABLE_NAME}
    USING hnsw (embedding {HNSW_OPS})
    WITH (m = {M_VALUE}, ef_construction = {EF_CONSTRUCTION})
""")
# Tempo para o PostgreSQL descarregar os buffers para o disco
print("Aguardando persistencia (10s)...")
time.sleep(10)

cur.execute("CHECKPOINT;")

def tamanho(sql):
    cur.execute(sql)
    v = cur.fetchone()[0]
    return bytes_to_mb(v or 0)

tabela_mb = tamanho(f"SELECT pg_relation_size('{TABLE_NAME}')")
hnsw_mb   = tamanho(f"SELECT pg_relation_size('{INDEX_NAME}')")
pk_mb     = tamanho(f"""SELECT pg_relation_size(i.indexrelid) FROM pg_index i
                         WHERE i.indrelid = '{TABLE_NAME}'::regclass AND i.indisprimary""")
toast_mb  = tamanho(f"""SELECT pg_total_relation_size(c.reltoastrelid) FROM pg_class c
                         WHERE c.oid = '{TABLE_NAME}'::regclass AND c.reltoastrelid <> 0""")
total_mb  = tamanho(f"SELECT pg_total_relation_size('{TABLE_NAME}')")
outros_mb = max(0.0, total_mb - tabela_mb - hnsw_mb - pk_mb - toast_mb)
wal_mb    = get_pg_wal_mb(POSTGRES_CONTAINER)

with open(CSV_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["DB", "Metric", "Tabela_MB", "HNSW_MB", "Chave_primaria_MB", "TOAST_MB",
                     "Outros_MB", "Total_MB", "WAL_cluster_MB"])
    writer.writerow(["pgvector", args.metric.upper(), round(tabela_mb, 2), round(hnsw_mb, 2),
                     round(pk_mb, 2), round(toast_mb, 2), round(outros_mb, 2),
                     round(total_mb, 2), round(wal_mb, 2)])

cur.close()
conn.close()

print(f"\nFeito! -> {CSV_FILE}")
print(f"Tabela               : {tabela_mb:.2f} MiB")
print(f"Índice HNSW          : {hnsw_mb:.2f} MiB")
print(f"Índice chave primária: {pk_mb:.2f} MiB")
print(f"TOAST                : {toast_mb:.2f} MiB")
print(f"Outros (FSM, VM)     : {outros_mb:.2f} MiB")
print(f"Total da tabela      : {total_mb:.2f} MiB")
print(f"WAL do cluster       : {wal_mb:.2f} MiB (fora do total)")
