"""
Figura 2.3: distância euclidiana e similaridade de cosseno entre dois vetores
a duas dimensões, A = (1, 2) e B = (2, 3).

Saída: images/comparar_euclides_cosine.png
Uso:   python gerar_figura_metricas.py
"""
from pathlib import Path

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

ax[0].text(0.1, 4.1, f'Distância Euclidiana: {dist_euclidiana:.2f}', fontsize=11, fontweight='bold')
ax[0].text(A[0] - 0.15, A[1], 'A', fontsize=12, fontweight='bold')
ax[0].text(B[0] + 0.08, B[1], 'B', fontsize=12, fontweight='bold')

ax[0].set_xlim(0, 3)
ax[0].set_ylim(0, 4.5)   # espaço por cima para o texto
ax[0].grid(True)
ax[0].set_xlabel('Eixo X')
ax[0].set_ylabel('Eixo Y')
ax[0].set_title('Distância Euclidiana')
ax[0].legend(loc='upper right')

# (b) similaridade de cosseno, com a projeção de A sobre B a tracejado
ax[1].quiver(0, 0, A[0], A[1], angles='xy', scale_units='xy', scale=1, color='red', label='Vetor A (1, 2)')
ax[1].quiver(0, 0, B[0], B[1], angles='xy', scale_units='xy', scale=1, color='blue', label='Vetor B (2, 3)')

proj_b_A = (np.dot(A, B) / np.dot(B, B)) * B
ax[1].plot([A[0], proj_b_A[0]], [A[1], proj_b_A[1]], color='gray', linestyle='--', label='Projeção de Ângulo')

ax[1].text(0.1, 4.1, f'Similaridade de Cosseno: {cos_sim:.2f}', fontsize=11, fontweight='bold')
ax[1].text(A[0] - 0.15, A[1], 'A', fontsize=12, fontweight='bold')
ax[1].text(B[0] + 0.08, B[1], 'B', fontsize=12, fontweight='bold')

ax[1].set_xlim(0, 3)
ax[1].set_ylim(0, 4.5)
ax[1].grid(True)
ax[1].set_xlabel('Eixo X')
ax[1].set_ylabel('Eixo Y')
ax[1].set_title('Similaridade de Cosseno')
ax[1].legend(loc='upper right')

plt.tight_layout()
Path("images").mkdir(exist_ok=True)
plt.savefig("images/comparar_euclides_cosine.png", dpi=600)
plt.show()
