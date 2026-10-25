"""
Gera os subconjuntos do SIFT1M: os primeiros N vetores da base, para
N = 100, 1 000, 10 000, 100 000 e 1 000 000 (sift/subsets/sift_base_<N>.npy).

Uso: python3 scripts/gerar_subconjuntos.py
"""
import numpy as np
from pathlib import Path

# ficheiros e escalas
INPUT_BASE = Path("sift/sift_base.npy")
OUTPUT_DIR = Path("sift/subsets")

SUBSET_SIZES = [100, 1_000, 10_000, 100_000, 1_000_000]

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"A carregar a base: {INPUT_BASE}")
    base_vectors = np.load(INPUT_BASE)

    total = base_vectors.shape[0]
    print(f"Vetores disponíveis: {total}")

    for size in SUBSET_SIZES:
        if size > total:
            print(f"Aviso: a ignorar a escala {size} (a base não tem vetores suficientes)")
            continue

        subset = base_vectors[:size]  # determinístico
        output_file = OUTPUT_DIR / f"sift_base_{size}.npy"

        np.save(output_file, subset)
        print(f"Criado {output_file}, com a forma {subset.shape}")

    print("Subconjuntos gerados.")

if __name__ == "__main__":
    main()
