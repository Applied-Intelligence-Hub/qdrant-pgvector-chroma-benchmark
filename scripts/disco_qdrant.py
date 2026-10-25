"""
Consumo de disco do Qdrant (1M vetores, m=16, ef_construct=200).

Só mede depois de a indexação terminar (estado green e todos os vetores
indexados) e de o tamanho da pasta estabilizar. Na versão 1.9.4 os vetores
ficam numa base RocksDB comprimida dentro de cada segmento, por isso o total
pode ser menor do que os vetores em bruto (488 MiB).

Uso: python disco_qdrant.py --metric l2
"""
import argparse
import csv
import subprocess
import time

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (CollectionStatus, Distance, HnswConfigDiff,
                                  OptimizersConfigDiff, VectorParams)

parser = argparse.ArgumentParser()
parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
args = parser.parse_args()

CONTAINER_NAME = "qdrant"
DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 1_000_000
DIM = 128
EF_CONSTRUCTION = 200
M_VALUE = 16
TIMEOUT_INDEXACAO_S = 1800   # limite de segurança: 30 min

if args.metric == "l2":
    COLLECTION_NAME, DISTANCE, NORMALIZE = "disk_test_l2", Distance.EUCLID, False
    CSV_FILE = "disk_qdrant_l2.csv"
else:
    COLLECTION_NAME, DISTANCE, NORMALIZE = "disk_test_cosine", Distance.COSINE, True
    CSV_FILE = "disk_qdrant_cosine.csv"

COLLECTION_DIR = f"/qdrant/storage/collections/{COLLECTION_NAME}"


def get_size_mb(path):
    """Tamanho em MiB de uma diretoria dentro do contentor (du -sb)."""
    result = subprocess.run(["docker", "exec", CONTAINER_NAME, "du", "-sb", path],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"du falhou em {path}: {result.stderr.strip()}")
    return int(result.stdout.split()[0]) / (1024 * 1024)


def esperar_indexacao(client):
    """Espera até a coleção estar green, com o otimizador parado e todos os
    vetores indexados. Devolve o tempo de espera em segundos."""
    t0 = time.perf_counter()
    while True:
        info = client.get_collection(COLLECTION_NAME)
        if info.status == CollectionStatus.GREY:
            # Otimizações pendentes mas não iniciadas: forçar o arranque
            client.update_collection(COLLECTION_NAME,
                                     optimizer_config=OptimizersConfigDiff())
        indexados = info.indexed_vectors_count or 0
        pontos = info.points_count or 0
        print(f"  estado={info.status.value} otimizador={info.optimizer_status} "
              f"indexados={indexados}/{pontos} segmentos={info.segments_count}")
        if (info.status == CollectionStatus.GREEN
                and str(info.optimizer_status).lower().endswith("ok")
                and pontos == TOTAL_VECTORS
                and indexados >= pontos):
            return time.perf_counter() - t0
        if time.perf_counter() - t0 > TIMEOUT_INDEXACAO_S:
            raise TimeoutError("A indexação não terminou dentro do limite.")
        time.sleep(5)


def esperar_disco_estavel(intervalo_s=10, tentativas=30):
    """Mede a diretoria até duas leituras seguidas coincidirem."""
    anterior = get_size_mb(COLLECTION_DIR)
    for _ in range(tentativas):
        time.sleep(intervalo_s)
        atual = get_size_mb(COLLECTION_DIR)
        print(f"  tamanho da coleção: {atual:.2f} MiB")
        if abs(atual - anterior) < 0.01:
            return atual
        anterior = atual
    raise TimeoutError("O tamanho em disco não estabilizou.")


client = QdrantClient(host="localhost", port=6333, timeout=300)
vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
if NORMALIZE:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vectors = vectors / norms

if client.collection_exists(COLLECTION_NAME):
    client.delete_collection(COLLECTION_NAME)

client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=DIM, distance=DISTANCE),
    hnsw_config=HnswConfigDiff(m=M_VALUE, ef_construct=EF_CONSTRUCTION),
)

print("A inserir vetores...")
client.upload_collection(collection_name=COLLECTION_NAME, vectors=vectors,
                         ids=list(range(TOTAL_VECTORS)), batch_size=10000)

print("A aguardar o fim da indexação...")
espera_s = esperar_indexacao(client)
print(f"Indexação concluída ({espera_s:.0f} s). A aguardar disco estável...")
total_mb = esperar_disco_estavel()

base_path = f"{COLLECTION_DIR}/0"
segments_mb = get_size_mb(f"{base_path}/segments")
wal_mb = get_size_mb(f"{base_path}/wal")
outros_mb = max(0.0, total_mb - segments_mb - wal_mb)

# decompor os segmentos pela listagem de ficheiros (du -ab): vector_index/ é o
# grafo HNSW e os *.sst são a base RocksDB onde ficam os vetores (comprimidos)
listagem = subprocess.run(["docker", "exec", CONTAINER_NAME, "du", "-ab",
                           f"{base_path}/segments"],
                          capture_output=True, text=True, check=True).stdout
grafo_b = sst_b = 0
for linha in listagem.splitlines():
    tamanho, caminho = linha.split(maxsplit=1)
    if caminho.endswith("/vector_index"):
        grafo_b += int(tamanho)
    elif caminho.endswith(".sst"):
        sst_b += int(tamanho)
grafo_mb = grafo_b / (1024 * 1024)
sst_mb = sst_b / (1024 * 1024)
restante_seg_mb = max(0.0, segments_mb - grafo_mb - sst_mb)

bruto_mb = TOTAL_VECTORS * DIM * 4 / (1024 * 1024)   # ~488,3 MiB (float32 sem compressão)
compressao = sst_mb / bruto_mb

with open(CSV_FILE, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["DB", "Metric", "Segments_MB", "Vetores_RocksDB_MB", "Grafo_HNSW_MB",
                "Restante_segmentos_MB", "WAL_MB", "Outros_MB", "Total_MB",
                "Total_sem_WAL_MB", "Vetores_brutos_MB", "Rácio_compressão",
                "Espera_indexacao_s"])
    w.writerow(["Qdrant", args.metric.upper(), round(segments_mb, 2), round(sst_mb, 2),
                round(grafo_mb, 2), round(restante_seg_mb, 2), round(wal_mb, 2),
                round(outros_mb, 2), round(total_mb, 2), round(total_mb - wal_mb, 2),
                round(bruto_mb, 2), round(compressao, 3), round(espera_s)])

print(f"\nFeito -> {CSV_FILE}")
print(f"Segmentos      : {segments_mb:.2f} MiB")
print(f"  vetores (RocksDB, comprimidos): {sst_mb:.2f} MiB "
      f"({compressao:.0%} dos {bruto_mb:.2f} MiB em bruto)")
print(f"  grafo HNSW                    : {grafo_mb:.2f} MiB")
print(f"  restante                      : {restante_seg_mb:.2f} MiB")
print(f"WAL            : {wal_mb:.2f} MiB")
print(f"Outros         : {outros_mb:.2f} MiB")
print(f"Total          : {total_mb:.2f} MiB")
