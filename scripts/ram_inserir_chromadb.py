"""
Insere 1M vetores no ChromaDB (coleção disk_test_<metrica>, m=16, ef_construction=200).

Usado com o monitorizar_ram.py para o perfil de RAM. A coleção fica criada para os
ensaios de latência, concorrência e arranque a frio.

A coleção é criada já com ef_search = 64, porque no ChromaDB esse valor tem de ser
definido na criação.

Uso: python ram_inserir_chromadb.py --metric l2
"""
import argparse
import time
import chromadb
import numpy as np

p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
args = p.parse_args()

DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 1_000_000
COLLECTION_NAME = f"disk_test_{args.metric}"
SPACE, NORMALIZE = ("l2", False) if args.metric == "l2" else ("cosine", True)

client = chromadb.HttpClient(host="localhost", port=8000)
BATCH_SIZE = client.get_max_batch_size()
print(f"A preparar coleção '{COLLECTION_NAME}' (pedidos de {BATCH_SIZE} vetores)...")
try:
    client.delete_collection(COLLECTION_NAME)
except Exception:
    pass

collection = client.create_collection(name=COLLECTION_NAME, metadata={
    "hnsw:space": SPACE, "hnsw:M": 16, "hnsw:construction_ef": 200, "hnsw:search_ef": 64})

vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
if NORMALIZE:
    n = np.linalg.norm(vectors, axis=1, keepdims=True); n[n == 0] = 1; vectors = vectors / n
vectors = vectors.tolist()

print("A inserir...")
t0 = time.perf_counter()
for i in range(0, TOTAL_VECTORS, BATCH_SIZE):
    lote = vectors[i:i + BATCH_SIZE]
    collection.add(embeddings=lote, ids=[str(j) for j in range(i, i + len(lote))])
    if (i // BATCH_SIZE) % 20 == 0:
        print(f"  {i + len(lote)} vetores inseridos...", flush=True)
collection.query(query_embeddings=[vectors[0]], n_results=10)
total = time.perf_counter() - t0

meta = client.get_collection(COLLECTION_NAME).metadata
print(f"\nConcluído em {total:.0f} s. count={collection.count()} metadata={meta}")
