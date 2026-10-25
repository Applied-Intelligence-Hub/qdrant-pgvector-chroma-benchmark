"""
Inserção em lote: ChromaDB | L2 ou Cosseno

Insere 100 000 vetores com lotes de 100 a 50 000 (3 réplicas por lote) e regista
a ingestão, a construção do índice e o tempo total até a coleção estar pronta.

O tamanho máximo de cada pedido é o que o servidor indica
(client.get_max_batch_size()); lotes maiores são divididos em pedidos desse
tamanho (coluna Pedido_efetivo). No fim faz-se uma consulta para garantir que a
coleção já está pesquisável quando o tempo pára.

Uso: python lote_inserir_chromadb.py --metric l2
"""
import argparse, csv, gc, statistics, time
import chromadb
import numpy as np

DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 100_000
BATCH_SIZES = [100, 1_000, 10_000, 50_000]
REPLICAS = 3
COLLECTION_NAME = "batch_test"

CFG = {"l2": ("l2", False, "resultados_batch_chromadb_L2.csv", "L2"),
       "cosine": ("cosine", True, "resultados_batch_chromadb_Cosine.csv", "Cosine")}


def main(metric):
    space, normalizar, csv_file, label = CFG[metric]
    vecs = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
    if normalizar:
        n = np.linalg.norm(vecs, axis=1, keepdims=True); n[n == 0] = 1; vecs = vecs / n
    vectors = vecs.tolist()
    ids = [str(i) for i in range(TOTAL_VECTORS)]

    client = chromadb.HttpClient(host="localhost", port=8000)
    max_batch = client.get_max_batch_size()
    print(f"Tamanho máximo de pedido indicado pelo servidor: {max_batch}", flush=True)

    with open(csv_file, "w", newline="") as f:
        csv.writer(f).writerow(["DB", "Metric", "Batch_Size", "Pedido_efetivo", "Replica",
                                "Ingestao_s", "Primeira_consulta_s", "Total_s", "Throughput_vec_s"])

    for b_size in BATCH_SIZES:
        pedido = min(b_size, max_batch)
        totais = []
        for rep in range(1, REPLICAS + 1):
            try:
                client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass
            col = client.create_collection(COLLECTION_NAME, metadata={
                "hnsw:space": space, "hnsw:M": 16,
                "hnsw:construction_ef": 200, "hnsw:search_ef": 64})
            print(f"[ChromaDB {label}] lote={b_size} rep={rep}: a correr...", flush=True)
            t0 = time.perf_counter()
            for i in range(0, TOTAL_VECTORS, b_size):
                fim = min(i + b_size, TOTAL_VECTORS)
                for j in range(i, fim, pedido):
                    k = min(j + pedido, fim)
                    col.add(embeddings=vectors[j:k], ids=ids[j:k])
            t1 = time.perf_counter()
            col.query(query_embeddings=[vectors[0]], n_results=10)
            t2 = time.perf_counter()
            ingest, consulta, total = t1 - t0, t2 - t1, t2 - t0
            totais.append(total)
            print(f"[ChromaDB {label}] lote={b_size} rep={rep}: ingestão {ingest:.2f}s + "
                  f"1.ª consulta {consulta:.2f}s = {total:.2f}s ({TOTAL_VECTORS/total:.0f} vec/s)")
            with open(csv_file, "a", newline="") as f:
                csv.writer(f).writerow(["ChromaDB", label, b_size, pedido, rep, round(ingest, 3),
                                        round(consulta, 3), round(total, 3),
                                        round(TOTAL_VECTORS / total, 1)])
            gc.collect()
        print(f"  mediana: {statistics.median(totais):.2f}s")
    client.delete_collection(COLLECTION_NAME)
    print(f"\nFeito -> {csv_file}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
    main(p.parse_args().metric)
