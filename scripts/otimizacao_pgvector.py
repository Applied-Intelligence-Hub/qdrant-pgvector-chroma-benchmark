"""
Otimização dos parâmetros do HNSW: pgvector | L2 ou Cosseno

Testa m em {16, 24, 32} e ef_search em {64, 128, 256} (ef_construction = 200).
Para cada combinação mede o Recall@10 e o p50 em 1 000 consultas e a memória do
contentor separada em memória do processo (anon), cache de ficheiros (file) e
memória partilhada (shmem). Uma execução por configuração.

Uso: python otimizacao_pgvector.py --metric l2
"""
import argparse
import numpy as np
import time
import csv
import psycopg2
import docker
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector

# --- Configuração ---
DATA_FILE        = "sift/subsets/sift_base_1000000.npy"
QUERIES_FILE     = "sift/sift_query.npy"
PG_TABLE         = "items_optimize"
TOTAL_VECTORS    = 1_000_000
NUM_QUERIES      = 1_000
EF_CONSTRUCTION  = 200
WARMUP_QUERIES   = 50
CONTAINER_NAME   = "pgvector"

M_VALUES         = [16, 24, 32]
EF_SEARCH_VALUES = [64, 128, 256]

METRIC_CONFIG = {
    "l2": {
        "hnsw_ops":    "vector_l2_ops",
        "query_op":    "<->",
        "gt_file":     "sift/gt/gt_1000000.npy",
        "normalize":   False,
        "csv_file":    "resultados_otimizacao_pgvector_L2.csv",
        "label":       "L2",
    },
    "cosine": {
        "hnsw_ops":    "vector_cosine_ops",
        "query_op":    "<=>",
        "gt_file":     "sift/gt_cosine/gt_1000000.npy",
        "normalize":   True,
        "csv_file":    "resultados_otimizacao_pgvector_Cosine.csv",
        "label":       "Cosine",
    },
}

# --- Funções auxiliares ---
def normalize(vectors: np.ndarray) -> np.ndarray:
    """Normaliza vetores para norma unitária."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vectors / norms

def calc_recall(results, ground_truth, k=10) -> float:
    hits = sum(len(set(res) & set(gt_row[:k])) for res, gt_row in zip(results, ground_truth))
    return (hits / (len(results) * k)) * 100

def medir_memoria(container_name: str, amostras: int = 5, intervalo_s: float = 0.5) -> dict:
    """Memória do contentor (cgroup v2), medida da mesma forma nos três motores.

    Devolve, em GB, a mediana de várias leituras de:
      - Total_GB: memory_stats.usage (total);
      - Anon_GB:  memória anónima, alocada pelo próprio processo (heap);
      - File_GB:  páginas de ficheiros em cache (inclui ficheiros mapeados);
      - Shmem_GB: memória partilhada (contabilizada dentro de File_GB).
    """
    cont = docker.from_env().containers.get(container_name)
    leituras = []
    for _ in range(amostras):
        ms = cont.stats(stream=False)["memory_stats"]
        st = ms.get("stats", {})
        leituras.append((ms["usage"], st.get("anon", 0), st.get("file", 0), st.get("shmem", 0)))
        time.sleep(intervalo_s)
    gb = 1024 ** 3
    med = lambda i: float(np.median([l[i] for l in leituras])) / gb
    return {"Total_GB": med(0), "Anon_GB": med(1), "File_GB": med(2), "Shmem_GB": med(3)}

# --- Ciclo principal ---
def run_optimization(metric: str):
    cfg = METRIC_CONFIG[metric]
    conn = psycopg2.connect(dbname="vectordb", user="postgres", password="postgres", host="localhost")
    conn.autocommit = True
    cur = conn.cursor()
    register_vector(conn)
    
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    cur.execute("SET maintenance_work_mem = '1GB';")
    
    print("A carregar dados para a RAM...")
    base_vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
    queries      = np.load(QUERIES_FILE)[:NUM_QUERIES].astype(np.float32)
    gt           = np.load(cfg["gt_file"])[:NUM_QUERIES]
    
    if cfg["normalize"]:
        base_vectors = normalize(base_vectors)
        queries      = normalize(queries)
    
    # Criar tabela
    print(f"\n[FASE 1] A criar tabela '{PG_TABLE}'...")
    cur.execute(f"DROP TABLE IF EXISTS {PG_TABLE};")
    cur.execute(f"CREATE TABLE {PG_TABLE} (id INTEGER PRIMARY KEY, embedding vector(128));")
    
    print(f"A inserir {TOTAL_VECTORS:,} vetores (Bulk insert, pode demorar)...")
    data_to_insert = [(i, v.tolist()) for i, v in enumerate(base_vectors)]
    execute_values(cur, f"INSERT INTO {PG_TABLE} (id, embedding) VALUES %s", data_to_insert, page_size=10_000)
    
    # Criar o header do CSV
    with open(cfg["csv_file"], "w", newline="") as f:
        csv.writer(f).writerow(["DB", "Metric", "m", "ef_search", "Recall_10", "p50_ms", "Total_GB", "Anon_GB", "File_GB", "Shmem_GB"])
    
    query_sql = f"SELECT id FROM {PG_TABLE} ORDER BY embedding {cfg['query_op']} %s::vector LIMIT 10;"
    
    for m in M_VALUES:
        print(f"\n=== m={m} | A construir índice HNSW ===")
        cur.execute("DROP INDEX IF EXISTS idx_optimize;")
        cur.execute(f"""
            CREATE INDEX idx_optimize ON {PG_TABLE} 
            USING hnsw (embedding {cfg['hnsw_ops']}) 
            WITH (m = {m}, ef_construction = {EF_CONSTRUCTION});
        """)
        print(f"  Índice pronto.")
        
        cur.execute("SET enable_seqscan = off;")  # Forçar uso do índice
        
        for ef_s in EF_SEARCH_VALUES:
            print(f"  -> ef_search={ef_s}")
            cur.execute(f"SET hnsw.ef_search = {ef_s};")
            
            # Warmup para estabilizar a buffer pool
            for q in queries[:WARMUP_QUERIES]:
                cur.execute(query_sql, (q.tolist(),))
                cur.fetchall()
            
            latencies, results = [], []
            for q in queries:
                t0 = time.perf_counter()
                cur.execute(query_sql, (q.tolist(),))
                results.append([row[0] for row in cur.fetchall()])
                latencies.append((time.perf_counter() - t0) * 1000)
            
            recall = calc_recall(results, gt)
            p50    = np.percentile(latencies, 50)
            
            mem = medir_memoria(CONTAINER_NAME)
            print(f"     Recall={recall:.2f}% | p50={p50:.2f}ms | total={mem['Total_GB']:.2f} GB "
                  f"(anon {mem['Anon_GB']:.2f}, file {mem['File_GB']:.2f}, shmem {mem['Shmem_GB']:.2f})")
            
            with open(cfg["csv_file"], "a", newline="") as f:
                csv.writer(f).writerow([
                    "pgvector", cfg["label"], m, ef_s, 
                    round(recall, 2), round(p50, 2), round(mem["Total_GB"], 3), round(mem["Anon_GB"], 3), round(mem["File_GB"], 3), round(mem["Shmem_GB"], 3)
                ])
    
    cur.close()
    conn.close()
    print(f"\nFeito! Ficheiro: {cfg['csv_file']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Otimização pgvector")
    parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
    args = parser.parse_args()
    run_optimization(args.metric)
