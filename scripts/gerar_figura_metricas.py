"""
Figura 2.3: distância euclidiana e similaridade de cosseno entre dois vetores
a duas dimensões, A = (1, 2) e B = (2, 3).

Saída: images/comparar_euclides_cosine.png
Uso:   python gerar_figura_metricas.py
"""
from pathlib import Path

from matplotlib.patches import Arc
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

import matplotlib.pyplot as plt
import numpy as np

A = np.array([1, 2])
B = np.array([2, 3])

dist_euclidiana = np.linalg.norm(A - B)
cos_sim = np.dot(A, B) / (np.linalg.norm(A) * np.linalg.norm(B))

fig, ax = plt.subplots(1, 2, figsize=(12, 6))

# (a) distância euclidiana
ax[0].quiver(0, 0, A[0], A[1], angles='xy', scale_units='xy', scale=1, color='red', label='Ponto A (1, 2)')
ax[0].quiver(0, 0, B[0], B[1], angles='xy', scale_units='xy', scale=1, color='blue', label='Ponto B (2, 3)')
ax[0].plot([A[0], B[0]], [A[1], B[1]], 'k--', label='Distância Euclidiana')

ax[0].text(0.1, 4.1, f'Distância Euclidiana: {dist_euclidiana:.2f}'.replace('.', ','), fontsize=11, fontweight='bold')
ax[0].text(A[0] - 0.15, A[1], 'A', fontsize=12, fontweight='bold')
ax[0].text(B[0] + 0.08, B[1], 'B', fontsize=12, fontweight='bold')

ax[0].set_xlim(0, 3)
ax[0].set_ylim(0, 4.5)   # espaço por cima para o texto
ax[0].grid(True)
ax[0].set_xlabel('Eixo x')
ax[0].set_ylabel('Eixo y')
ax[0].set_title('Distância Euclidiana')
ax[0].legend(loc='upper right')

# (b) similaridade de cosseno: o ângulo θ entre A e B
ax[1].quiver(0, 0, A[0], A[1], angles='xy', scale_units='xy', scale=1, color='red', label='Vetor A (1, 2)')
ax[1].quiver(0, 0, B[0], B[1], angles='xy', scale_units='xy', scale=1, color='blue', label='Vetor B (2, 3)')

ang_A = np.degrees(np.arctan2(A[1], A[0]))
ang_B = np.degrees(np.arctan2(B[1], B[0]))
ax[1].add_patch(Arc((0, 0), 3.0, 3.0, angle=0, theta1=ang_B, theta2=ang_A, color='dimgray', lw=1.8))
meio = np.radians((ang_A + ang_B) / 2)
ax[1].text(1.72 * np.cos(meio), 1.72 * np.sin(meio), 'θ', fontsize=14, ha='center', va='center')
ax[1].plot([], [], color='dimgray', lw=1.8, label='Ângulo θ entre A e B')

ax[1].text(0.1, 4.1, f'Similaridade de Cosseno: {cos_sim:.2f}'.replace('.', ','), fontsize=11, fontweight='bold')
ax[1].text(A[0] - 0.15, A[1], 'A', fontsize=12, fontweight='bold')
ax[1].text(B[0] + 0.08, B[1], 'B', fontsize=12, fontweight='bold')

ax[1].set_xlim(0, 3)
ax[1].set_ylim(0, 4.5)
ax[1].grid(True)
ax[1].set_xlabel('Eixo x')
ax[1].set_ylabel('Eixo y')
ax[1].set_title('Similaridade de Cosseno')
ax[1].legend(loc='upper right')

virgula = FuncFormatter(lambda v, _: f'{v:.1f}'.replace('.', ','))
for eixo in ax:
    eixo.xaxis.set_major_formatter(virgula)
    eixo.yaxis.set_major_formatter(virgula)

plt.tight_layout()
Path("images").mkdir(exist_ok=True)
plt.savefig("images/comparar_euclides_cosine.png", dpi=600)

