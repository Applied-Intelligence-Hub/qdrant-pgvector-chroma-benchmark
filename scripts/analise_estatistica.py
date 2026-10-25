"""
Análise estatística do benchmark de base.

Para cada métrica, escala e par de motores, compara as 10 réplicas do p50 e do p95
com o teste de Mann-Whitney U (exato, bilateral) e aplica a correção de Holm aos 60
testes. Calcula também o delta de Cliff e o estimador de Hodges-Lehmann, e as
medianas das réplicas usadas nas tabelas.

Entrada: results_<motor>_<metrica>.csv
Saída:   medianas_base_l2.csv, medianas_base_cosine.csv, testes_base.csv

Uso: python analise_estatistica.py [pasta dos results_*.csv]
"""
import csv
import itertools
import os
import sys

import numpy as np
from scipy.stats import mannwhitneyu

PASTA = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else os.getcwd()   # pasta dos results_*.csv
MOTORES = ["Qdrant", "pgvector", "ChromaDB"]
METRICAS = ["l2", "cosine"]
ESTATISTICAS = ["p50_ms", "p95_ms"]
COLUNAS = ["Ingest_Time_s", "Index_Build_s", "Ready_Time_s", "RAM_Baseline_GB",
           "RAM_Build_Peak_GB", "RAM_Query_Avg_GB", "p50_ms", "p95_ms", "p99_ms",
           "QPS", "Recall@10"]


def ler(motor, metrica):
    with open(os.path.join(PASTA, f"results_{motor.lower()}_{metrica}.csv")) as f:
        return list(csv.DictReader(f))


def cliff_delta(a, b):
    a, b = np.asarray(a), np.asarray(b)
    maiores = np.sum(a[:, None] > b[None, :])
    menores = np.sum(a[:, None] < b[None, :])
    return (maiores - menores) / (len(a) * len(b))


def hodges_lehmann(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return float(np.median((a[:, None] - b[None, :]).ravel()))


def holm(pvalores):
    m = len(pvalores)
    ordem = np.argsort(pvalores)
    ajust = np.empty(m)
    acumulado = 0.0
    for k, i in enumerate(ordem):
        acumulado = max(acumulado, min(1.0, (m - k) * pvalores[i]))
        ajust[i] = acumulado
    return ajust


dados = {(mo, me): ler(mo, me) for mo in MOTORES for me in METRICAS}
escalas = sorted({int(r["Scale"]) for r in dados[("Qdrant", "l2")]})

# medianas das réplicas
for me in METRICAS:
    with open(os.path.join(PASTA, f"medianas_base_{me}.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Motor", "Scale"] + COLUNAS)
        for mo in MOTORES:
            for n in escalas:
                rs = [r for r in dados[(mo, me)] if int(r["Scale"]) == n]
                linha = [mo, n]
                for c in COLUNAS:
                    v = [float(r[c]) for r in rs if r[c] != ""]
                    linha.append(f"{np.median(v):.4f}" if v else "")
                w.writerow(linha)

# testes
testes = []
for me in METRICAS:
    for n in escalas:
        for a, b in itertools.combinations(MOTORES, 2):
            for est in ESTATISTICAS:
                va = [float(r[est]) for r in dados[(a, me)] if int(r["Scale"]) == n]
                vb = [float(r[est]) for r in dados[(b, me)] if int(r["Scale"]) == n]
                u, p = mannwhitneyu(va, vb, alternative="two-sided", method="exact")
                hl = hodges_lehmann(va, vb)
                testes.append({"Metrica": me, "Scale": n, "Par": f"{a} vs {b}", "Estatistica": est,
                               "Mediana_A": np.median(va), "Mediana_B": np.median(vb),
                               "U": u, "p": p, "Cliff_delta": cliff_delta(va, vb),
                               "HL_ms": hl, "Mais_rapido": a if hl < 0 else b})
p_holm = holm(np.array([t["p"] for t in testes]))
for t, ph in zip(testes, p_holm):
    t["p_Holm"] = ph

with open(os.path.join(PASTA, "testes_base.csv"), "w", newline="") as f:
    campos = ["Metrica", "Scale", "Par", "Estatistica", "Mediana_A", "Mediana_B", "U",
              "p", "p_Holm", "Cliff_delta", "HL_ms", "Mais_rapido"]
    w = csv.DictWriter(f, fieldnames=campos)
    w.writeheader()
    for t in testes:
        w.writerow({k: (f"{t[k]:.6g}" if isinstance(t[k], (float, np.floating)) else t[k]) for k in campos})

sig = sum(1 for t in testes if t["p_Holm"] < 0.05)
print(f"{len(testes)} testes; {sig} significativos após a correção de Holm (alfa = 0,05).")
print("Ficheiros: medianas_base_l2.csv, medianas_base_cosine.csv, testes_base.csv")
