# Dataset preparation (SIFT1M)

The experiments use the SIFT1M dataset from the INRIA TEXMEX corpus (http://corpus-texmex.irisa.fr/),
distributed as `sift.tar.gz`, with `sift_base.fvecs` (1,000,000 vectors), `sift_query.fvecs`
(10,000 queries) and `sift_groundtruth.ivecs` (the 100 nearest neighbours of each query, L2).

```bash
wget ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz
tar -xvzf sift.tar.gz
python3 scripts/converter_sift.py
python3 scripts/gerar_subconjuntos.py
python3 scripts/gerar_ground_truth_l2.py
python3 scripts/gerar_ground_truth_cosseno.py
```

`scripts/preparar_dados.py` runs all these steps at once and checks the shape of every file at the end.

1. **`converter_sift.py`** — Each `.fvecs`/`.ivecs` record stores its dimension (an `int32`)
   followed by the values; the script removes the dimension and saves `sift/sift_base.npy`,
   `sift/sift_query.npy` and `sift/sift_gt.npy` (the official ground truth).
2. **`gerar_subconjuntos.py`** — For each scale N = 100, 1,000, 10,000, 100,000 and 1,000,000,
   saves the first N base vectors as `sift/subsets/sift_base_<N>.npy`. The selection is deterministic.
3. **`gerar_ground_truth_l2.py`** — SIFT1M only provides the ground truth of the full dataset in L2.
   For each subset, this script computes the 10 nearest neighbours (L2) of each query by exact
   (brute-force) search, with queries in batches of 50 and the base in blocks of 50,000 vectors to
   limit memory, and saves `sift/gt/gt_<N>.npy`.
4. **`gerar_ground_truth_cosseno.py`** — The same for the Cosine similarity: queries and base vectors are
   normalised to unit length, as in the experiment scripts, and the 10 most similar vectors of each
   query (dot product) are saved in `sift/gt_cosine/gt_<N>.npy`.

Ids are positions in the subset, starting at 0. The experiment scripts use these 10 neighbours to
compute Recall@10.

| File | Shape |
|---|---|
| `sift/sift_query.npy` | (10000, 128) |
| `sift/subsets/sift_base_<N>.npy` | (N, 128) |
| `sift/gt/gt_<N>.npy`, `sift/gt_cosine/gt_<N>.npy` | (10000, 10) |

**Check.** The exact ground truth of the full dataset in L2 can be compared with the official one:

```bash
python3 -c "import numpy as np; a=np.load('sift/sift_gt.npy')[:,:10]; b=np.load('sift/gt/gt_1000000.npy'); print(np.mean([len(set(x)&set(y))/10 for x,y in zip(a,b)]))"
```

The result should be 1.0 (or very close, because of ties in the distances).
