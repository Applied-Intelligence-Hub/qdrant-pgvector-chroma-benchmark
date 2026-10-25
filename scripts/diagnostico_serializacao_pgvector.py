"""
Tamanho e tempo de preparação dos vetores enviados ao pgvector.

Pede ao psycopg2 o texto SQL que enviaria para os 100 000 vetores do ensaio de
inserção em lote, sem o enviar, e mede quantos bytes tem e quanto tempo demora a
preparar, em L2 (valores inteiros) e em Cosseno (vetores normalizados).

Saída: diagnostico_serializacao_pgvector.csv
Uso:   python diagnostico_serializacao_pgvector.py
"""
import csv
import time

import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector

conn = psycopg2.connect(dbname="vectordb", user="postgres", password="postgres", host="localhost")
register_vector(conn)
cur = conn.cursor()

base = np.load("sift/subsets/sift_base_100000.npy").astype(np.float32)
normas = np.linalg.norm(base, axis=1, keepdims=True); normas[normas == 0] = 1
vetores = {"L2": base, "Cosine": (base / normas).astype(np.float32)}

resultados = []
for metrica, vecs in vetores.items():
    t0 = time.perf_counter()
    total = sum(len(cur.mogrify("(%s)", (v,))) for v in vecs)
    t = time.perf_counter() - t0
    exemplo = cur.mogrify("%s", (vecs[0],)).decode()[:70]
    resultados.append((metrica, total, total / len(vecs), t))
    print(f"{metrica:6s}: {total/1e6:6.1f} MB de texto ({total/len(vecs):5.0f} bytes por vetor) | "
          f"preparação no cliente: {t:5.2f} s | exemplo: {exemplo}…", flush=True)

l2, cos = resultados
print(f"\nCosseno/L2: {cos[1]/l2[1]:.2f} vezes mais bytes; {cos[3]-l2[3]:+.2f} s de preparação no cliente.")
with open("diagnostico_serializacao_pgvector.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Metrica", "Bytes_total", "Bytes_por_vetor", "Preparacao_cliente_s"])
    for r in resultados: w.writerow([r[0], r[1], round(r[2], 1), round(r[3], 3)])
print("Feito -> diagnostico_serializacao_pgvector.csv")
conn.close()
