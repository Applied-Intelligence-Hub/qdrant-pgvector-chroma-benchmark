"""
Otimização dos parâmetros do HNSW: Qdrant | L2 ou Cosseno

Testa m em {16, 24, 32} e ef_search em {64, 128, 256} (ef_construction = 200).
Para cada combinação mede o Recall@10 e o p50 em 1 000 consultas e a memória do
contentor separada em memória do processo (anon), cache de ficheiros (file) e
memória partilhada (shmem). Uma execução por configuração.

Uso: python otimizacao_qdrant.py --metric l2
"""
import argparse
import numpy as np
import time
import csv
import docker
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, HnswConfigDiff, SearchParams

#Config
CONTAINER_NAME  = "qdrant"
DATA_FILE       = "sift/subsets/sift_base_1000000.npy"
QUERIES_FILE    = "sift/sift_query.npy"
TOTAL_VECTORS   = 1_000_000
NUM_QUERIES     = 1_000
EF_CONSTRUCTION = 200
COLLECTION_NAME = "optimize_test"

M_VALUES         = [16, 24, 32]
EF_SEARCH_VALUES = [64, 128, 256]

METRIC_CONFIG = {
    "l2": {
        "distance":  Distance.EUCLID,
        "gt_file":   "sift/gt/gt_1000000.npy",
        "normalize": False,
        "csv_file":  "resultados_otimizacao_qdrant_L2.csv",
        "label":     "L2",
    },
    "cosine": {
        "distance":  Distance.COSINE,
        "gt_file":   "sift/gt_cosine/gt_1000000.npy",
        "normalize": True,
        "csv_file":  "resultados_otimizacao_qdrant_Cosine.csv",
        "label":     "Cosine",
    },
}

#Utils
def normalize(vectors: np.ndarray) -> np.ndarray:
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

#Bench
def run_optimization(metric: str):
    cfg = METRIC_CONFIG[metric]
    client = QdrantClient(host="localhost", port=6333, timeout=300)

    print("A carregar dados...")
    base_vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
    queries      = np.load(QUERIES_FILE)[:NUM_QUERIES].astype(np.float32)
    gt           = np.load(cfg["gt_file"])[:NUM_QUERIES]

    if cfg["normalize"]:
        base_vectors = normalize(base_vectors)
        queries      = normalize(queries)

    ids = list(range(TOTAL_VECTORS))

    with open(cfg["csv_file"], "w", newline="") as f:
        csv.writer(f).writerow(["DB", "Metric", "m", "ef_search", "Recall_10", "p50_ms", "Total_GB", "Anon_GB", "File_GB", "Shmem_GB"])

    for m in M_VALUES:
        print(f"\n=== m={m} ===")
        if client.collection_exists(COLLECTION_NAME):
            client.delete_collection(COLLECTION_NAME)

        #Força a flag on_disk = True, de forma a evitar que o Qdrant aloque toda a sua estrutura,
        # diretamente no heap do Rust, obriga assim a partilhar recursos via mmap
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=128, distance=cfg["distance"], on_disk=True),
            hnsw_config=HnswConfigDiff(m=m, ef_construct=EF_CONSTRUCTION, on_disk=True)
        )

        print(f"A fazer upload de {TOTAL_VECTORS} vetores...")
        client.upload_collection(collection_name=COLLECTION_NAME, vectors=base_vectors, ids=ids, batch_size=10_000)

        print("A aguardar que o indice fique pronto (status: green)...")
        while True:
            info = client.get_collection(COLLECTION_NAME)
            if str(info.status).lower() == "green": break
            time.sleep(5)

        # Ao fazer a ingestão, acumula-se muito "lixo" temporário na RAM
        # Restart para limpar a RAM de ingestão e ficar só com o índice mapeado
        print("A reiniciar o contentor Qdrant para limpar RAM de ingestao...")
        client.close() 
        docker_client = docker.from_env()
        docker_client.containers.get(CONTAINER_NAME).restart()
        time.sleep(10)
        
        client = QdrantClient(host="localhost", port=6333, timeout=300)
        
        # Warmup para forçar o SO a carregar os ficheiros mmap para a Page Cache
        print("A executar warm-up (a carregar mmap para RAM)...")
        for q in queries[:100]:
            try:
                client.search(collection_name=COLLECTION_NAME, query_vector=q, limit=10, search_params=SearchParams(hnsw_ef=64))
            except Exception:
                time.sleep(2)


        for ef_s in EF_SEARCH_VALUES:
            print(f"  -> ef_search={ef_s}")
            latencies, results = [], []
            for q in queries:
                t0 = time.perf_counter()
                res = client.search(collection_name=COLLECTION_NAME, query_vector=q, limit=10, search_params=SearchParams(hnsw_ef=ef_s))
                latencies.append((time.perf_counter() - t0) * 1000)
                results.append([int(hit.id) for hit in res])

            recall = calc_recall(results, gt)
            p50    = np.percentile(latencies, 50)
            mem    = medir_memoria(CONTAINER_NAME)
            print(f"     Recall={recall:.2f}% | p50={p50:.2f}ms | total={mem['Total_GB']:.2f} GB "
                  f"(anon {mem['Anon_GB']:.2f}, file {mem['File_GB']:.2f})")

            with open(cfg["csv_file"], "a", newline="") as f:
                csv.writer(f).writerow([
                    "Qdrant", cfg["label"], m, ef_s, 
                    round(recall, 2), round(p50, 2), round(mem["Total_GB"], 3), round(mem["Anon_GB"], 3), round(mem["File_GB"], 3), round(mem["Shmem_GB"], 3)
                ])

    print(f"\nBenchmark feito! Resultados em: {cfg['csv_file']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
    args = parser.parse_args()
    run_optimization(args.metric)
