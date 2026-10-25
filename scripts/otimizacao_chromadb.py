"""
Otimização dos parâmetros do HNSW: ChromaDB | L2 ou Cosseno

Testa m em {16, 24, 32} e ef_search em {64, 128, 256} (ef_construction = 200).
Para cada combinação mede o Recall@10 e o p50 em 1 000 consultas, e a memória do
contentor separada em memória do processo (anon), cache de ficheiros (file) e
memória partilhada (shmem). Uma execução por configuração.

No ChromaDB 1.x o m e o ef_construction só se definem na criação da coleção, e o
ef_search muda-se com modify(configuration=...). Por isso é criada uma coleção
por valor de m e o script confirma a configuração em vigor antes de cada medição.

Uso: python otimizacao_chromadb.py --metric l2
"""
import httpx
import argparse
import chromadb
import numpy as np
import time
import csv
import gc
import docker

#Config
CONTAINER_NAME   = "chromadb"
DATA_FILE        = "sift/subsets/sift_base_1000000.npy"
QUERIES_FILE     = "sift/sift_query.npy"
TOTAL_VECTORS    = 1_000_000
NUM_QUERIES      = 1_000
EF_CONSTRUCTION  = 200
COLLECTION_NAME  = "optimize_test"
WARMUP_QUERIES   = 50

M_VALUES         = [16, 24, 32]
EF_SEARCH_VALUES = [64, 128, 256]

METRIC_CONFIG = {
    "l2": {
        "hnsw_space":  "l2",
        "gt_file":     "sift/gt/gt_1000000.npy",
        "normalize":   False,
        "csv_file":    "resultados_otimizacao_chromadb_L2.csv",
        "label":       "L2",
    },
    "cosine": {
        "hnsw_space":  "cosine",
        "gt_file":     "sift/gt_cosine/gt_1000000.npy",
        "normalize":   True,
        "csv_file":    "resultados_otimizacao_chromadb_Cosine.csv",
        "label":       "Cosine",
    },
}

# Utils
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

def ler_hnsw(collection) -> dict:
    """Devolve a configuração HNSW em vigor na coleção."""
    cfg = getattr(collection, "configuration", None) or getattr(collection, "configuration_json", None) or {}
    hnsw = cfg.get("hnsw") if isinstance(cfg, dict) else None
    if not hnsw:
        raise SystemExit(f"Não foi possível ler a configuração HNSW da coleção: {cfg}")
    return hnsw

def restart_container_and_connect(docker_client, container_name: str, host="localhost", port=8000):
    print("  A reiniciar container Docker...")
    container = docker_client.containers.get(container_name)
    container.restart()
    time.sleep(10) # Dar tempo ao SQLite e ao hnswlib para iniciarem as ligações
    
    client = chromadb.HttpClient(host=host, port=port)
    deadline = time.time() + 120 
    while time.time() < deadline:
        try:
            client.list_collections() 
            return client
        except (httpx.ReadError, Exception):
            time.sleep(2)
    raise Exception("O ChromaDB demorou mais de 2 minutos a reiniciar.")

# Main
def run_optimization(metric: str):
    cfg          = METRIC_CONFIG[metric]
    docker_client = docker.from_env()

    print("A carregar dados para a RAM...")
    base_vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
    queries_arr  = np.load(QUERIES_FILE)[:NUM_QUERIES].astype(np.float32)
    gt           = np.load(cfg["gt_file"])[:NUM_QUERIES]

    if cfg["normalize"]:
        base_vectors = normalize(base_vectors)
        queries_arr  = normalize(queries_arr)

    #O ChromaDB faz o processo da API via Python, convertendo o Numpy array para uma lista pura
    base_list    = base_vectors.tolist()
    queries_list = queries_arr.tolist()
    ids          = [str(i) for i in range(TOTAL_VECTORS)]

    with open(cfg["csv_file"], "w", newline="") as f:
        csv.writer(f).writerow(["DB", "Metric", "m", "ef_search", "Recall_10", "p50_ms", "Total_GB", "Anon_GB", "File_GB", "Shmem_GB"])

    client = None
    for m in M_VALUES:
        print(f"\n=== m={m} | A construir indice HNSW ===")
        client = restart_container_and_connect(docker_client, CONTAINER_NAME)
        
        try: client.delete_collection(COLLECTION_NAME)
        except Exception: pass

        collection = client.create_collection(
            name=COLLECTION_NAME,
            configuration={"hnsw": {
                "space":           cfg["hnsw_space"],
                "max_neighbors":   m,
                "ef_construction": EF_CONSTRUCTION,
                "ef_search":       EF_SEARCH_VALUES[0],
            }}
        )
        hnsw = ler_hnsw(collection)
        if hnsw.get("max_neighbors") != m or hnsw.get("ef_construction") != EF_CONSTRUCTION:
            raise SystemExit(f"A coleção não ficou com m={m} e ef_construction={EF_CONSTRUCTION}: {hnsw}")

        max_batch = client.get_max_batch_size()
        print(f"  A inserir {TOTAL_VECTORS:,} vetores (pedidos de {max_batch})...")
        for i in range(0, TOTAL_VECTORS, max_batch):
            end = min(i + max_batch, TOTAL_VECTORS)
            collection.add(embeddings=base_list[i:end], ids=ids[i:end])

        print("A aguardar 15s para as threads de background do ChromaDB estabilizarem...")
        time.sleep(15)
        
        print("  Indice pronto.")

        recalls = []
        for ef_s in EF_SEARCH_VALUES:
            print(f"\n  -> ef_search={ef_s}")

            # Alteração através da configuração (API do ChromaDB 1.x)
            collection.modify(configuration={"hnsw": {"ef_search": ef_s}})
            # reiniciar para o índice ser carregado com a nova configuração
            client = restart_container_and_connect(docker_client, CONTAINER_NAME)
            collection = client.get_collection(COLLECTION_NAME)
            hnsw = ler_hnsw(collection)
            if hnsw.get("ef_search") != ef_s or hnsw.get("max_neighbors") != m:
                raise SystemExit(f"Configuração em vigor diferente da pretendida: {hnsw}")
            print(f"     configuração em vigor: m={hnsw['max_neighbors']}, ef_search={hnsw['ef_search']}")
            
            # Como a cache do disco e RAM caíram durante o restart, é preciso realizar um warmup
            print("A reconstruir a cache da RAM...")
            for q in queries_list[:500]:
                collection.query(query_embeddings=[q], n_results=10)

            #Medição real
            latencies, results = [], []
            for q in queries_list:
                t0      = time.perf_counter()
                res_raw = collection.query(query_embeddings=[q], n_results=10)
                latencies.append((time.perf_counter() - t0) * 1000)
                results.append([int(x) for x in res_raw["ids"][0]])

            recall = calc_recall(results, gt)
            recalls.append(recall)
            p50    = np.percentile(latencies, 50)
            mem    = medir_memoria(CONTAINER_NAME)
            print(f"     Recall={recall:.2f}% | p50={p50:.2f}ms | total={mem['Total_GB']:.2f} GB "
                  f"(anon {mem['Anon_GB']:.2f}, file {mem['File_GB']:.2f})")

            with open(cfg["csv_file"], "a", newline="") as f:
                csv.writer(f).writerow([
                    "ChromaDB", cfg["label"], m, ef_s, 
                    round(recall, 2), round(p50, 2), round(mem["Total_GB"], 3), round(mem["Anon_GB"], 3), round(mem["File_GB"], 3), round(mem["Shmem_GB"], 3)
                ])
        
        if not all(b > a for a, b in zip(recalls, recalls[1:])):
            print(f"  AVISO: o Recall@10 não aumentou com o ef_search ({recalls}). "
                  "A alteração pode não ter tido efeito.")
        gc.collect()

    print(f"\nFeito! Ficheiro: {cfg['csv_file']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimizar ChromaDB")
    parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
    args = parser.parse_args()
    run_optimization(args.metric)
