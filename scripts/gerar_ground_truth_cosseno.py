"""
Ground truth (Cosseno) de cada subconjunto do SIFT1M, por força bruta.

Guarda os 10 vizinhos mais semelhantes de cada consulta em sift/gt_cosine/gt_<N>.npy.

Uso: python3 scripts/gerar_ground_truth_cosseno.py
"""
import numpy as np
import os
from tqdm import tqdm

BASE_DIR = os.getcwd()   # pasta de onde se corre o script

SCALES = [100, 1_000, 10_000, 100_000, 1_000_000]

QUERY_FILE = os.path.join(BASE_DIR, "sift/sift_query.npy")
OUTPUT_DIR = os.path.join(BASE_DIR, "sift/gt_cosine")

TOP_K = 10
QUERY_BATCH = 100

os.makedirs(OUTPUT_DIR, exist_ok=True)

# vetores com norma 1
def normalize(vectors):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / norms

def generate_gt_cosine():

    print("A carregar as consultas...")
    queries = np.load(QUERY_FILE)
    queries = normalize(queries)

    for n in SCALES:
        print(f"\nEscala {n}: a calcular o ground truth (Cosseno)...")

        base = np.load(os.path.join(BASE_DIR, f"sift/subsets/sift_base_{n}.npy"))
        base = normalize(base)

        gt = np.zeros((len(queries), TOP_K), dtype=np.int32)

        for i in tqdm(range(0, len(queries), QUERY_BATCH)):
            q_batch = queries[i:i + QUERY_BATCH]

            # com os vetores normalizados, a similaridade de cosseno é o produto interno
            sims = np.dot(q_batch, base.T)

            # os 10 mais semelhantes, sem ordenar a linha inteira
            idx = np.argpartition(-sims, TOP_K, axis=1)[:, :TOP_K]

            # ordenar só esses 10
            sorted_idx = np.argsort(-sims[np.arange(len(q_batch))[:, None], idx], axis=1)
            topk = idx[np.arange(len(q_batch))[:, None], sorted_idx]

            gt[i:i + len(q_batch)] = topk

        out_path = os.path.join(OUTPUT_DIR, f"gt_{n}.npy")
        np.save(out_path, gt)

        print(f"Guardado: {out_path}")

if __name__ == "__main__":
    generate_gt_cosine()
