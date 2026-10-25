"""
Inserção em lote: Qdrant | L2 ou Cosseno

Insere 100 000 vetores com lotes de 100 a 50 000 (3 réplicas por lote) e regista
a ingestão, a construção do índice e o tempo total até a coleção estar pronta.

O indexing_threshold é baixado para INDEXING_THRESHOLD_KB para o HNSW ser
construído com 100 000 vetores, e o tempo só pára no estado green. Lotes acima
de MAX_QDRANT_BATCH são enviados em pedidos desse tamanho (coluna Pedido_efetivo).

Uso: python lote_inserir_qdrant.py --metric l2
"""
import argparse, csv, gc, statistics, time
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (CollectionStatus, Distance, HnswConfigDiff,
                                  OptimizersConfigDiff, VectorParams)

DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 100_000
BATCH_SIZES = [100, 1_000, 10_000, 50_000]
REPLICAS = 3
COLLECTION_NAME = "batch_test"
M, EF_CONSTRUCTION = 16, 200
MAX_QDRANT_BATCH = 10_000
INDEXING_THRESHOLD_KB = 1000
TIMEOUT_S = 1800

CFG = {"l2": (Distance.EUCLID, False, "resultados_batch_qdrant_L2.csv", "L2"),
       "cosine": (Distance.COSINE, True, "resultados_batch_qdrant_Cosine.csv", "Cosine")}


def esperar_indexacao(client):
    t0 = time.perf_counter()
    ultimo_aviso = 0.0
    while True:
        info = client.get_collection(COLLECTION_NAME)
        decorrido = time.perf_counter() - t0
        if decorrido - ultimo_aviso >= 15:
            print(f"    a indexar... {info.indexed_vectors_count or 0}/{info.points_count or 0} "
                  f"({decorrido:.0f}s)", flush=True)
            ultimo_aviso = decorrido
        if info.status == CollectionStatus.GREY:
            client.update_collection(COLLECTION_NAME, optimizer_config=OptimizersConfigDiff())
        if (info.status == CollectionStatus.GREEN
                and str(info.optimizer_status).lower().endswith("ok")
                and (info.points_count or 0) == TOTAL_VECTORS
                and (info.indexed_vectors_count or 0) >= TOTAL_VECTORS):
            return
        if time.perf_counter() - t0 > TIMEOUT_S:
            raise TimeoutError("Indexação não terminou dentro do limite.")
        time.sleep(0.5)


def main(metric):
    distance, normalizar, csv_file, label = CFG[metric]
    client = QdrantClient(host="localhost", port=6333, timeout=300)
    vecs = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
    if normalizar:
        n = np.linalg.norm(vecs, axis=1, keepdims=True); n[n == 0] = 1; vecs = vecs / n
    ids = list(range(TOTAL_VECTORS))

    with open(csv_file, "w", newline="") as f:
        csv.writer(f).writerow(["DB", "Metric", "Batch_Size", "Pedido_efetivo", "Replica",
                                "Ingestao_s", "Indexacao_s", "Total_s", "Throughput_vec_s"])

    for b_size in BATCH_SIZES:
        pedido = min(b_size, MAX_QDRANT_BATCH)
        totais = []
        for rep in range(1, REPLICAS + 1):
            if client.collection_exists(COLLECTION_NAME):
                client.delete_collection(COLLECTION_NAME)
            client.create_collection(COLLECTION_NAME,
                                     vectors_config=VectorParams(size=128, distance=distance),
                                     hnsw_config=HnswConfigDiff(m=M, ef_construct=EF_CONSTRUCTION),
                                     optimizers_config=OptimizersConfigDiff(
                                         indexing_threshold=INDEXING_THRESHOLD_KB))
            print(f"[Qdrant {label}] lote={b_size} rep={rep}: a correr...", flush=True)
            t0 = time.perf_counter()
            client.upload_collection(COLLECTION_NAME, vectors=vecs, ids=ids,
                                     batch_size=pedido, parallel=1)
            t1 = time.perf_counter()
            esperar_indexacao(client)
            t2 = time.perf_counter()
            ingest, index, total = t1 - t0, t2 - t1, t2 - t0
            totais.append(total)
            print(f"[Qdrant {label}] lote={b_size} rep={rep}: ingestão {ingest:.2f}s + "
                  f"indexação {index:.2f}s = {total:.2f}s ({TOTAL_VECTORS/total:.0f} vec/s)")
            with open(csv_file, "a", newline="") as f:
                csv.writer(f).writerow(["Qdrant", label, b_size, pedido, rep, round(ingest, 3),
                                        round(index, 3), round(total, 3),
                                        round(TOTAL_VECTORS / total, 1)])
            gc.collect()
        print(f"  mediana: {statistics.median(totais):.2f}s")
    client.delete_collection(COLLECTION_NAME)
    print(f"\nFeito -> {csv_file}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
    main(p.parse_args().metric)
