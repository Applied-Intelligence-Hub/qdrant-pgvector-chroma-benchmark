"""
Insere 1M vetores no Qdrant (coleção disk_test_<metrica>, m=16, ef_construction=200).

Usado com o monitorizar_ram.py para o perfil de RAM. A coleção fica criada para os
ensaios de latência, concorrência e arranque a frio.

O script só termina quando o índice está construído (estado green), para a série
de RAM incluir a construção.

Uso: python ram_inserir_qdrant.py --metric l2
"""
import argparse
import time

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (CollectionStatus, Distance, HnswConfigDiff,
                                  OptimizersConfigDiff, VectorParams)

parser = argparse.ArgumentParser()
parser.add_argument("--metric", choices=["l2", "cosine"], required=True)
args = parser.parse_args()

DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 1_000_000
TIMEOUT_INDEXACAO_S = 1800

if args.metric == "l2":
    COLLECTION_NAME, DISTANCE, NORMALIZE = "disk_test_l2", Distance.EUCLID, False
else:
    COLLECTION_NAME, DISTANCE, NORMALIZE = "disk_test_cosine", Distance.COSINE, True


def esperar_indexacao(client):
    """Espera até a coleção estar green, com o otimizador parado e todos os
    vetores indexados. Devolve o tempo de espera em segundos."""
    t0 = time.perf_counter()
    while True:
        info = client.get_collection(COLLECTION_NAME)
        if info.status == CollectionStatus.GREY:
            client.update_collection(COLLECTION_NAME,
                                     optimizer_config=OptimizersConfigDiff())
        indexados = info.indexed_vectors_count or 0
        pontos = info.points_count or 0
        print(f"  estado={info.status.value} indexados={indexados}/{pontos}")
        if (info.status == CollectionStatus.GREEN
                and str(info.optimizer_status).lower().endswith("ok")
                and pontos == TOTAL_VECTORS
                and indexados >= pontos):
            return time.perf_counter() - t0
        if time.perf_counter() - t0 > TIMEOUT_INDEXACAO_S:
            raise TimeoutError("A indexação não terminou dentro do limite.")
        time.sleep(5)


client = QdrantClient(host="localhost", port=6333, timeout=300)

print(f"A preparar coleção '{COLLECTION_NAME}' no Qdrant...")
if client.collection_exists(collection_name=COLLECTION_NAME):
    client.delete_collection(collection_name=COLLECTION_NAME)

client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=128, distance=DISTANCE),
    hnsw_config=HnswConfigDiff(m=16, ef_construct=200),
)

print("A carregar vetores do disco...")
vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
if NORMALIZE:
    print("A normalizar vetores (Cosseno)...")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1
    vectors = vectors / norms

print("A inserir vetores...")
t0 = time.perf_counter()
client.upload_collection(collection_name=COLLECTION_NAME, vectors=vectors,
                         ids=list(range(TOTAL_VECTORS)), batch_size=5000)
upload_s = time.perf_counter() - t0

print("Upload concluído. A aguardar a construção do índice HNSW...")
espera_s = esperar_indexacao(client)

print(f"\nConcluído. Upload: {upload_s:.0f} s | indexação após o upload: {espera_s:.0f} s")
