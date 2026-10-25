"""
Ground truth (L2) de cada subconjunto do SIFT1M, por força bruta.

Guarda os 10 vizinhos mais próximos de cada consulta em sift/gt/gt_<N>.npy.

Uso: python3 scripts/gerar_ground_truth_l2.py
"""
import numpy as np
import os
from tqdm import tqdm

# escalas, ficheiros e parâmetros
SCALES = [100, 1_000, 10_000, 100_000, 1_000_000]

QUERY_FILE = "sift/sift_query.npy"
BASE_PATH = "sift/subsets"
OUTPUT_PATH = "sift/gt"

K = 10
QUERY_BATCH = 50
BASE_CHUNK = 50_000  # blocos da base, para limitar a memória

# os k vizinhos mais próximos de cada consulta, percorrendo a base por blocos
def compute_ground_truth(base, queries, k=10):
    gt = []

    for i in tqdm(range(0, len(queries), QUERY_BATCH)):
        q_batch = queries[i:i + QUERY_BATCH]

        # guardar melhores resultados globais
        best_dists = np.full((len(q_batch), k), np.inf)
        best_indices = np.full((len(q_batch), k), -1)

        for j in range(0, len(base), BASE_CHUNK):
            base_chunk = base[j:j + BASE_CHUNK]

            # distâncias L2 ao quadrado
            q_norm = np.sum(q_batch**2, axis=1, keepdims=True)
            x_norm = np.sum(base_chunk**2, axis=1)

            dists = q_norm + x_norm - 2 * np.dot(q_batch, base_chunk.T)

            # juntar aos melhores dos blocos anteriores
            combined_dists = np.concatenate([best_dists, dists], axis=1)
            combined_indices = np.concatenate([
                best_indices,
                np.arange(j, j + len(base_chunk))[None, :].repeat(len(q_batch), axis=0)
            ], axis=1)

            # ficar com os k melhores até aqui
            idx = np.argsort(combined_dists, axis=1)[:, :k]

            best_dists = np.take_along_axis(combined_dists, idx, axis=1)
            best_indices = np.take_along_axis(combined_indices, idx, axis=1)

        gt.extend(best_indices)

    return np.array(gt)


def main():
    os.makedirs(OUTPUT_PATH, exist_ok=True)

    print("A carregar as consultas...")
    queries = np.load(QUERY_FILE)

    for n in SCALES:
        print(f"\nEscala {n}: a calcular o ground truth (L2)...")

        base = np.load(f"{BASE_PATH}/sift_base_{n}.npy")

        gt = compute_ground_truth(base, queries, k=K)

        output_file = f"{OUTPUT_PATH}/gt_{n}.npy"
        np.save(output_file, gt)

        print(f"Guardado: {output_file}")


if __name__ == "__main__":
    main()