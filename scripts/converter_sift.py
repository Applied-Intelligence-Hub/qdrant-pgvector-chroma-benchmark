"""
Converte os ficheiros .fvecs/.ivecs do SIFT1M para .npy.

Lê sift/sift_base.fvecs, sift/sift_query.fvecs e sift/sift_groundtruth.ivecs e
escreve sift/sift_base.npy, sift/sift_query.npy e sift/sift_gt.npy.

Uso: python3 scripts/converter_sift.py
"""
import numpy as np


def read_fvecs(fname):
    with open(fname, 'rb') as f:
        data = f.read()
    dim = np.frombuffer(data, dtype=np.int32)[0]
    vecs = np.frombuffer(data, dtype=np.float32).reshape(-1, dim + 1)
    return vecs[:, 1:]


def read_ivecs(fname):
    with open(fname, 'rb') as f:
        data = f.read()
    dim = np.frombuffer(data, dtype=np.int32)[0]
    vecs = np.frombuffer(data, dtype=np.int32).reshape(-1, dim + 1)
    return vecs[:, 1:]


base = read_fvecs("sift/sift_base.fvecs")
query = read_fvecs("sift/sift_query.fvecs")
gt = read_ivecs("sift/sift_groundtruth.ivecs")

np.save("sift/sift_base.npy", base)
np.save("sift/sift_query.npy", query)
np.save("sift/sift_gt.npy", gt)

print("Conversão concluída:")
print("Base:", base.shape)
print("Query:", query.shape)
print("GT:", gt.shape)
