"""
Consumo de disco do ChromaDB (1M vetores, m=16, ef_construction=200).

Mede os ficheiros do volume /data do servidor: as pastas de segmento do índice
(hnswlib), a base chroma.sqlite3 e, à parte, o WAL do SQLite. A instância tem de
estar vazia antes de começar, para só serem medidos os ficheiros desta coleção.

Também escreve disk_chromadb_ficheiros_indice_<metrica>.csv com o tamanho de cada
ficheiro do índice, que o gerar_figuras.py usa para separar vetores, grafo e ids.

Uso: python disco_chromadb.py --metric l2
"""
import argparse
import csv
import re
import subprocess
import time

import chromadb
import numpy as np

p = argparse.ArgumentParser(); p.add_argument("--metric", choices=["l2", "cosine"], required=True)
args = p.parse_args()

CONTAINER = "chromadb"
DATA_DIR = "/data"
DATA_FILE = "sift/subsets/sift_base_1000000.npy"
TOTAL_VECTORS = 1_000_000
DIM = 128
COLLECTION_NAME = f"disk_test_{args.metric}"
SPACE, NORMALIZE = ("l2", False) if args.metric == "l2" else ("cosine", True)
CSV_FILE = f"disk_chromadb_{args.metric}.csv"
CSV_FICHEIROS = f"disk_chromadb_ficheiros_indice_{args.metric}.csv"
FICHEIROS_HNSW = ["data_level0.bin", "link_lists.bin", "length.bin", "header.bin", "index_metadata.pickle"]
UUID = re.compile(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/")


def listar_ficheiros():
    """Devolve [(tamanho_bytes, caminho)] de todos os ficheiros em /data."""
    out = subprocess.run(["docker", "exec", CONTAINER, "find", DATA_DIR, "-type", "f",
                          "-exec", "du", "-b", "{}", "+"],
                         capture_output=True, text=True, check=True).stdout
    return [(int(t), c) for t, c in (l.split(maxsplit=1) for l in out.splitlines())]


def total_mb():
    return sum(t for t, _ in listar_ficheiros()) / (1024 * 1024)


def esperar_disco_estavel(intervalo_s=10, tentativas=60):
    anterior = total_mb()
    for _ in range(tentativas):
        time.sleep(intervalo_s)
        atual = total_mb()
        print(f"  tamanho de /data: {atual:.2f} MiB", flush=True)
        if abs(atual - anterior) < 0.01:
            return
        anterior = atual
    raise TimeoutError("O tamanho em disco não estabilizou.")


client = chromadb.HttpClient(host="localhost", port=8000)
existentes = [c.name if hasattr(c, "name") else c for c in client.list_collections()]
if existentes:
    raise SystemExit(f"A instância do ChromaDB não está vazia: {existentes}.\n"
                     "Esvaziar o volume antes de medir (ver instruções).")

vectors = np.load(DATA_FILE)[:TOTAL_VECTORS].astype(np.float32)
if NORMALIZE:
    n = np.linalg.norm(vectors, axis=1, keepdims=True); n[n == 0] = 1; vectors = vectors / n
vectors = vectors.tolist()

col = client.create_collection(name=COLLECTION_NAME, metadata={
    "hnsw:space": SPACE, "hnsw:M": 16, "hnsw:construction_ef": 200, "hnsw:search_ef": 64})
batch = client.get_max_batch_size()
print(f"A inserir {TOTAL_VECTORS} vetores (pedidos de {batch})...")
for i in range(0, TOTAL_VECTORS, batch):
    lote = vectors[i:i + batch]
    col.add(embeddings=lote, ids=[str(j) for j in range(i, i + len(lote))])
    if (i // batch) % 20 == 0:
        print(f"  {i + len(lote)} vetores inseridos...", flush=True)
col.query(query_embeddings=[vectors[0]], n_results=10)
print(f"count = {col.count()}. A aguardar disco estável...")
esperar_disco_estavel()

hnsw_b = sqlite_b = wal_b = outros_b = 0
ficheiros_indice = {}
for tamanho, caminho in listar_ficheiros():
    if UUID.search(caminho) and caminho.rsplit("/", 1)[-1] in FICHEIROS_HNSW:
        nome_f = caminho.rsplit("/", 1)[-1]
        ficheiros_indice[nome_f] = ficheiros_indice.get(nome_f, 0) + tamanho
    nome = caminho.rsplit("/", 1)[-1]
    if UUID.search(caminho):
        hnsw_b += tamanho
    elif nome == "chroma.sqlite3":
        sqlite_b += tamanho
    elif nome.startswith("chroma.sqlite3-"):
        wal_b += tamanho
    else:
        outros_b += tamanho
mb = lambda b: b / (1024 * 1024)
hnsw, sqlite, wal, outros = mb(hnsw_b), mb(sqlite_b), mb(wal_b), mb(outros_b)
total = hnsw + sqlite + wal + outros
bruto = TOTAL_VECTORS * DIM * 4 / (1024 * 1024)

with open(CSV_FILE, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["DB", "Metric", "Indice_HNSW_MB", "SQLite_MB", "WAL_MB", "Outros_MB",
                "Total_MB", "Total_sem_WAL_MB", "Vetores_brutos_MB"])
    w.writerow(["ChromaDB", args.metric.upper(), round(hnsw, 2), round(sqlite, 2), round(wal, 2),
                round(outros, 2), round(total, 2), round(total - wal, 2), round(bruto, 2)])

faltam = [f for f in FICHEIROS_HNSW if f not in ficheiros_indice]
if faltam:
    raise SystemExit(f"Não foram encontrados os ficheiros do índice: {faltam}")
with open(CSV_FICHEIROS, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Ficheiro", "Bytes"])
    for nome_f in FICHEIROS_HNSW:
        w.writerow([nome_f, ficheiros_indice[nome_f]])
n_indice = ficheiros_indice["data_level0.bin"] // (DIM * 4 + 132 + 8)
print(f"\nVetores escritos no índice (data_level0.bin): {n_indice} de {TOTAL_VECTORS}")

print(f"\nFeito -> {CSV_FILE} e {CSV_FICHEIROS}")
print(f"Índice HNSW (segmentos): {hnsw:.2f} MiB")
print(f"SQLite                 : {sqlite:.2f} MiB")
print(f"WAL (-wal, -shm)       : {wal:.2f} MiB")
print(f"Outros                 : {outros:.2f} MiB")
print(f"Total                  : {total:.2f} MiB (sem WAL: {total - wal:.2f})")
