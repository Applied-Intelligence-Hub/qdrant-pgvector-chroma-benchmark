"""
Prepara o SIFT1M de uma vez: descarrega, extrai e corre os quatro scripts de
preparação pela ordem certa. No fim confirma que os ficheiros têm as dimensões
esperadas e compara o ground truth L2 do conjunto completo com o oficial.

Passos:
  1. descarrega e extrai sift.tar.gz para sift/ (salta se os ficheiros já existirem)
  2. converter_sift.py   .fvecs/.ivecs -> .npy
  3. gerar_subconjuntos.py    subconjuntos com os primeiros N vetores
  4. gerar_ground_truth_l2.py     ground truth L2
  5. gerar_ground_truth_cosseno.py     ground truth Cosseno

Uso (a partir da raiz do repositório):
  python3 scripts/preparar_dados.py
  python3 scripts/preparar_dados.py --sem-download     # se o sift/ já tiver os .fvecs/.ivecs
"""
import argparse
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

import numpy as np

URL = "ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz"
ESCALAS = [100, 1_000, 10_000, 100_000, 1_000_000]
SCRIPTS = ["converter_sift.py", "gerar_subconjuntos.py",
           "gerar_ground_truth_l2.py", "gerar_ground_truth_cosseno.py"]
PASTA_SCRIPTS = Path(__file__).resolve().parent
ORIGINAIS = ["sift_base.fvecs", "sift_query.fvecs", "sift_groundtruth.ivecs"]


def descarregar():
    if all((Path("sift") / f).exists() for f in ORIGINAIS):
        print("[1] Ficheiros originais já existem em sift/, a saltar o download.")
        return
    print(f"[1] A descarregar {URL} (cerca de 160 MB)...")
    urllib.request.urlretrieve(URL, "sift.tar.gz")
    with tarfile.open("sift.tar.gz") as t:
        t.extractall(".")
    print("    Extraído para sift/.")


def correr(n, script):
    print(f"[{n}] python3 {script}")
    r = subprocess.run([sys.executable, str(PASTA_SCRIPTS / script)])
    if r.returncode != 0:
        sys.exit(f"O {script} terminou com erro ({r.returncode}).")


def verificar():
    print("\n--- Verificação ---")
    erros = 0
    esperado = {"sift/sift_query.npy": (10_000, 128)}
    for n in ESCALAS:
        esperado[f"sift/subsets/sift_base_{n}.npy"] = (n, 128)
        esperado[f"sift/gt/gt_{n}.npy"] = (10_000, 10)
        esperado[f"sift/gt_cosine/gt_{n}.npy"] = (10_000, 10)
    for f, forma in esperado.items():
        p = Path(f)
        if not p.exists():
            print(f"  FALTA  {f}"); erros += 1; continue
        real = np.load(p, mmap_mode="r").shape
        ok = real == forma
        erros += not ok
        print(f"  {'ok   ' if ok else 'ERRO '}  {f:34s} {real}")
    oficial = np.load("sift/sift_gt.npy")[:, :10]
    calculado = np.load("sift/gt/gt_1000000.npy")
    igual = np.mean([len(set(a) & set(b)) / 10 for a, b in zip(oficial, calculado)]) * 100
    print(f"\n  gt_1000000 (L2) vs. ground truth oficial do SIFT1M: {igual:.2f}% de vizinhos em comum")
    print("\nTudo pronto." if erros == 0 else f"\n{erros} problema(s) encontrado(s).")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sem-download", action="store_true", help="não descarregar (usar os ficheiros que já estão em sift/)")
    a, _ = p.parse_known_args()
    if not a.sem_download:
        descarregar()
    for i, s in enumerate(SCRIPTS, start=2):
        correr(i, s)
    verificar()
