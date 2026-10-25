"""
Figura 2.1: pesquisa exata (força bruta) vs. pesquisa aproximada (ANN), com
pontos sintéticos a duas dimensões.

Saída: images/pesquisa_exata_vs_aproximada.png
Uso:   python gerar_figura_pesquisa.py
"""
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

rng = np.random.default_rng(42)   # semente fixa, para a figura sair sempre igual

# pontos e consulta
N_PONTOS = 60
pontos = rng.uniform(0, 10, size=(N_PONTOS, 2))
consulta = np.array([5.0, 5.0])

dists = np.linalg.norm(pontos - consulta, axis=1)
ordem = np.argsort(dists)

K = 5
verdadeiros = ordem[:K]     # os K vizinhos mais próximos de facto

# zona explorada pela pesquisa aproximada: um pouco ao lado da consulta, para
# um dos vizinhos ficar de fora (como numa travessia do grafo)
CENTRO_VIZINHANCA = consulta + np.array([-0.9, 0.3])
RAIO_VIZINHANCA = 2.6
d_centro = np.linalg.norm(pontos - CENTRO_VIZINHANCA, axis=1)
dentro = np.where(d_centro <= RAIO_VIZINHANCA)[0]
fora = [i for i in verdadeiros if i not in dentro]
falhado = fora[0] if fora else verdadeiros[K - 1]
encontrados = [i for i in verdadeiros if i != falhado]

COR_PONTO = "#b0b7c3"
COR_CONSULTA = "#c0392b"
COR_VIZINHO = "#27ae60"
COR_FALHADO = "#e67e22"
COR_LINHA_EX = "#95a5a6"
COR_LINHA_AP = "#2980b9"

fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))

# (a) pesquisa exata: a consulta é comparada com todos os pontos
ax = axes[0]
for p in pontos:
    ax.plot([consulta[0], p[0]], [consulta[1], p[1]],
            color=COR_LINHA_EX, linewidth=0.4, alpha=0.45, zorder=1)

ax.scatter(pontos[:, 0], pontos[:, 1], s=42, c=COR_PONTO,
           edgecolors="white", linewidths=0.8, zorder=2)
ax.scatter(pontos[verdadeiros, 0], pontos[verdadeiros, 1], s=90,
           c=COR_VIZINHO, edgecolors="white", linewidths=1.2, zorder=3,
           label=f"{K} vizinhos mais próximos")
ax.scatter(*consulta, s=190, c=COR_CONSULTA, marker="*",
           edgecolors="white", linewidths=1.0, zorder=4,
           label="Vetor de consulta")

ax.set_title("(a) Pesquisa exata (força bruta)", fontsize=12, pad=12)
ax.text(0.5, -0.13,
        f"Compara a consulta com os $N$ vetores da coleção:\n"
        f"{N_PONTOS} comparações, garantindo os {K} vizinhos corretos.",
        transform=ax.transAxes, ha="center", va="top", fontsize=9.5)

# marcar já aqui o vizinho que falha em (b)
ax.add_patch(Circle(pontos[falhado], 0.62, facecolor="none",
                    edgecolor=COR_FALHADO, linewidth=1.6,
                    linestyle="--", zorder=5))
ax.annotate("omitido em (b)",
            xy=pontos[falhado], xytext=(pontos[falhado, 0] + 1.5,
                                        pontos[falhado, 1] - 1.9),
            fontsize=8.5, color=COR_FALHADO, fontweight="bold",
            ha="center",
            arrowprops=dict(arrowstyle="->", color=COR_FALHADO,
                            linewidth=1.3, shrinkA=0, shrinkB=8),
            zorder=6)

# (b) pesquisa aproximada: só os pontos da zona explorada
ax = axes[1]
ax.add_patch(Circle(CENTRO_VIZINHANCA, RAIO_VIZINHANCA, facecolor="#eaf2fb",
                    edgecolor=COR_LINHA_AP, linewidth=1.2,
                    linestyle="--", alpha=0.85, zorder=0))

for i in dentro:
    ax.plot([consulta[0], pontos[i, 0]], [consulta[1], pontos[i, 1]],
            color=COR_LINHA_AP, linewidth=0.6, alpha=0.55, zorder=1)

ax.scatter(pontos[:, 0], pontos[:, 1], s=42, c=COR_PONTO,
           edgecolors="white", linewidths=0.8, zorder=2)
avaliados = [i for i in dentro if i not in verdadeiros]
ax.scatter(pontos[avaliados, 0], pontos[avaliados, 1], s=42,
           c=COR_LINHA_AP, alpha=0.45, edgecolors="white",
           linewidths=0.8, zorder=2, label="Avaliados, não selecionados")
ax.scatter(pontos[encontrados, 0], pontos[encontrados, 1], s=90,
           c=COR_VIZINHO, edgecolors="white", linewidths=1.2, zorder=3,
           label="Vizinhos recuperados")
ax.scatter(pontos[falhado, 0], pontos[falhado, 1], s=110,
           c=COR_FALHADO, marker="X", edgecolors="white", linewidths=1.0,
           zorder=3, label="Vizinho não recuperado")
ax.scatter(*consulta, s=190, c=COR_CONSULTA, marker="*",
           edgecolors="white", linewidths=1.0, zorder=4,
           label="Vetor de consulta")

ax.set_title("(b) Pesquisa aproximada (ANN)", fontsize=12, pad=12)
ax.text(0.5, -0.13,
        f"Explora apenas uma vizinhança: {len(dentro)} comparações.\n"
        f"Recupera {len(encontrados)} dos {K} vizinhos: "
        f"Recall@{K} = {len(encontrados)/K:.0%}.",
        transform=ax.transAxes, ha="center", va="top", fontsize=9.5)

for ax in axes:
    ax.set_xlim(-0.6, 10.6)
    ax.set_ylim(-0.6, 10.6)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for lado in ax.spines.values():
        lado.set_color("#cccccc")
    ax.legend(loc="upper left", fontsize=8.5, framealpha=0.95,
              borderpad=0.6, labelspacing=0.4)

plt.tight_layout()
plt.subplots_adjust(bottom=0.17)
Path("images").mkdir(exist_ok=True)
plt.savefig("images/pesquisa_exata_vs_aproximada.png", dpi=300,
            bbox_inches="tight", facecolor="white")
print("Figura gerada: images/pesquisa_exata_vs_aproximada.png")
