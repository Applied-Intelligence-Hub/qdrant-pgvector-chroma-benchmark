# Results: data dictionary

Final CSV files of the thesis, one folder per experiment. Every value in Chapter 4 comes from these files.
File and column names are in Portuguese or English, as written by the scripts; this page explains each column and its unit.

Conventions: `<engine>` is `qdrant`, `chromadb` or `pgvector`; `<metric>` is `l2` or `cosine` (`L2` or `Cosine` in some file names).
MB and GB are binary units (2^20 and 2^30 bytes); MiB is used for disk sizes. Decimal separator: point.

---

## `benchmark_base/` — Base benchmark (Section 4.1.1)

| File | Produced by | Used in |
|---|---|---|
| `results_<engine>_<metric>.csv` | `benchmark_base_<engine>.py` | Source of the medians and tests below |
| `medianas_base_<metric>.csv` | `analise_estatistica.py` | Tables 4.1 and 4.2; synthesis Tables 4.23 and 4.24 |
| `testes_base.csv` | `analise_estatistica.py` | Tables 4.3 and 4.4 |

**`results_<engine>_<metric>.csv`** — one row per replica (10) and scale (100 to 1,000,000 vectors):

| Column | Meaning | Unit |
|---|---|---|
| `Replicate` | Replica number | — |
| `Scale` | Number of vectors in the collection | vectors |
| `Ingest_Time_s` | Time to send the vectors | s |
| `Index_Build_s` | Time to build the HNSW index after the insertion (empty in ChromaDB, which updates the index during insertion) | s |
| `Ready_Time_s` | Time until the collection is searchable (insertion + index) | s |
| `RAM_Baseline_GB` | Container memory at idle, before the insertion | GB |
| `RAM_Build_Peak_GB` | Peak memory during insertion and index build, above idle | GB |
| `RAM_Query_Avg_GB` | Mean memory during the queries, above idle | GB |
| `p50_ms`, `p95_ms`, `p99_ms` | Latency percentiles of the 10,000 queries | ms |
| `QPS` | Sequential throughput | queries/s |
| `Recall@10` | Fraction of the 10 true neighbours returned | 0–1 |

**`medianas_base_<metric>.csv`** — the same columns, with the median of the 10 replicas per engine (`Motor`) and scale.

**`testes_base.csv`** — one row per metric, scale, pair of engines and statistic:

| Column | Meaning |
|---|---|
| `Metrica`, `Scale` | Metric and scale |
| `Par` | Pair compared, as "A vs B" |
| `Estatistica` | Statistic compared over the 10 replicas (`p50_ms` or `p95_ms`) |
| `Mediana_A`, `Mediana_B` | Median of the 10 replicas of each engine (ms) |
| `U`, `p` | Exact Mann-Whitney U statistic and its two-sided p-value |
| `p_Holm` | p-value after Holm's correction over the 60 tests |
| `Cliff_delta` | Cliff's delta (effect size, −1 to 1; negative means A is faster) |
| `HL_ms` | Hodges-Lehmann estimate of the difference A − B (ms) |
| `Mais_rapido` | Engine with the lower median |

---

## `latency/` — Detailed latency and diagnostics (Section 4.1.2)

| File | Produced by | Used in |
|---|---|---|
| `latencias_<engine>_<metric>.csv` | `latencia_<engine>.py` | Figures 4.1 and 4.2 |
| `latencias_<engine>_<metric>_resumo.csv` | `latencia_<engine>.py` | Tables 4.5 and 4.6 |
| `diagnostico_qdrant_<metric>.csv` | `diagnostico_qdrant.py` | Table 4.7 |
| `diagnostico_pgvector_<metric>.csv` | `diagnostico_pgvector.py` | Table 4.8 |

| File | Columns |
|---|---|
| `latencias_*.csv` | `Replica` (1–5), `Query_ID` (0–9,999), `Latency_ms` (latency of each query, measured in the client) |
| `latencias_*_resumo.csv` | `Motor`, `Metrica`, `Replica`, percentiles `p10` to `p99_9` and `Max` (ms), `Skewness` and `Kurtosis` of the distribution of each replica |
| `diagnostico_qdrant_*.csv` | `Replica`, `Query_ID`, `Cliente_ms` (latency of a direct HTTP request, in the client), `Servidor_ms` (search time reported by Qdrant in the response) |
| `diagnostico_pgvector_*.csv` | `Consulta` (query number), `Cliente_ms` (latency in the client), `Planeamento_ms` and `Execucao_ms` (planning and execution time in PostgreSQL, from `EXPLAIN ANALYZE`) |

---

## `ram_profiling/` — RAM profiling (Section 4.1.3)

| File | Produced by | Used in |
|---|---|---|
| `ram_<engine>_<metric>.csv` | `monitorizar_ram.py` with `ram_inserir_<engine>.py` | Figure 4.3, Tables 4.9 and 4.10 |

Columns: `Tempo_Segundos` (time since the start of the recording, s) and `RAM_MB` (container memory as reported by `docker stats`, i.e. total memory minus inactive file cache, MB). The first row is the idle value; increases in the thesis are relative to it.

---

## `optimization/` — Parameter optimization (Section 4.1.4)

| File | Produced by | Used in |
|---|---|---|
| `resultados_otimizacao_<engine>_<Metric>.csv` | `otimizacao_<engine>.py` | Tables 4.11 and 4.12, Figure 4.4 |

| Column | Meaning | Unit |
|---|---|---|
| `DB`, `Metric` | Engine and metric | — |
| `m`, `ef_search` | HNSW parameters tested (`ef_construction` = 200) | — |
| `Recall_10` | Recall@10 over 1,000 queries | % |
| `p50_ms` | Median latency over the same queries | ms |
| `Total_GB` | Total container memory | GB |
| `Anon_GB` | Anonymous memory (allocated by the process) | GB |
| `File_GB` | File cache charged to the container | GB |
| `Shmem_GB` | Shared memory (PostgreSQL `shared_buffers`) | GB |

The "own memory" in the thesis tables is `Anon_GB` (plus `Shmem_GB` for pgvector).

---

## `batch_insertion/` — Batch insertion (Section 4.1.5)

| File | Produced by | Used in |
|---|---|---|
| `resultados_batch_<engine>_<Metric>.csv` | `lote_inserir_<engine>.py` | Tables 4.13 and 4.14, Figures 4.5 and 4.6 |
| `diagnostico_serializacao_pgvector.csv` | `diagnostico_serializacao_pgvector.py` | Text of Section 4.1.5 |

**`resultados_batch_*.csv`** — one row per batch size and replica (3):

| Column | Meaning | Unit |
|---|---|---|
| `Batch_Size` | Batch size requested | vectors |
| `Pedido_efetivo` | Size of each request actually sent (capped by Qdrant and ChromaDB) | vectors |
| `Replica` | Replica number | — |
| `Ingestao_s` | Time to send the 100,000 vectors | s |
| `Indexacao_s` | Time to build the index (Qdrant and pgvector) | s |
| `Primeira_consulta_s` | Time of a first query after the insertion (ChromaDB, to make sure the collection is searchable) | s |
| `Total_s` | Time until the collection is searchable | s |
| `Throughput_vec_s` | 100,000 / `Total_s` | vectors/s |

**`diagnostico_serializacao_pgvector.csv`** — `Metrica`, `Bytes_total` and `Bytes_por_vetor` (size of the SQL text prepared by `psycopg2` for the 100,000 vectors, bytes), `Preparacao_cliente_s` (time to prepare it in the client, s).

---

## `cold_warm/` — Cold start vs. warm cache (Section 4.1.6)

| File | Produced by | Used in |
|---|---|---|
| `resultados_cold_warm_<engine>_<Metric>.csv` | `arranque_frio_<engine>.py` | Tables 4.15 and 4.16; synthesis Tables 4.23 and 4.24 |

One row per replica (10):

| Column | Meaning | Unit |
|---|---|---|
| `Arranque_s` | From container start until the engine and the collection are available (checked every 0.1 s) | s |
| `First_Resp_Cold_ms`, `First_Resp_Warm_ms` | Latency of the first query of the cold and warm phases | ms |
| `Cold_First10_Mean_ms` | Mean latency of the first 10 cold queries | ms |
| `p50_Cold_ms`, `p95_Cold_ms`, `p50_Warm_ms`, `p95_Warm_ms` | Latency percentiles of the 1,000 queries of each phase | ms |
| `Recall_Cold`, `Recall_Warm` | Recall@10 of each phase | % |
| `Excesso_Frio_s` | Extra time of the cold phase over the warm phase: sum of the 1,000 cold latencies minus the sum of the 1,000 warm ones (0 if negative) | s |

The synthesis tables report "container start to first answer" as the median, over the replicas, of `Arranque_s` + `First_Resp_Cold_ms` / 1000.

---

## `disk/` — Disk usage (Section 4.1.7)

| File | Produced by | Used in |
|---|---|---|
| `disk_<engine>_<metric>.csv` | `disco_<engine>.py` | Tables 4.17 and 4.18, Figures 4.7 and 4.8 |
| `disk_chromadb_ficheiros_indice_<metric>.csv` | `disco_chromadb.py` | Split of the ChromaDB index in Figures 4.7 and 4.8 |

All sizes in MiB.

| Engine | Columns |
|---|---|
| Qdrant | `Segments_MB` (segment folders), `Vetores_RocksDB_MB` (vectors, in the compressed RocksDB store), `Grafo_HNSW_MB` (HNSW graph), `Restante_segmentos_MB`, `WAL_MB`, `Outros_MB`, `Total_MB`, `Total_sem_WAL_MB`, `Vetores_brutos_MB` (raw size of the vectors, 488 MiB), `Rácio_compressão`, `Espera_indexacao_s` (time waited until the index was complete, before measuring, s) |
| ChromaDB | `Indice_HNSW_MB` (hnswlib index folders), `SQLite_MB`, `WAL_MB` (SQLite write-ahead log), `Outros_MB`, `Total_MB`, `Total_sem_WAL_MB`, `Vetores_brutos_MB` |
| pgvector | `Tabela_MB`, `HNSW_MB`, `Chave_primaria_MB`, `TOAST_MB`, `Outros_MB`, `Total_MB` (from `pg_total_relation_size`), `WAL_cluster_MB` (WAL of the whole cluster, not included in the total) |

`disk_chromadb_ficheiros_indice_*.csv` lists the size in bytes (`Bytes`) of each hnswlib file (`Ficheiro`): `data_level0.bin`, `link_lists.bin`, `length.bin`, `header.bin` and `index_metadata.pickle`.

---

## `concurrency/` — Concurrency (Section 4.1.8)

| File | Produced by | Used in |
|---|---|---|
| `resultados_concorrencia_<engine>_<metric>.csv` | `escalabilidade_<engine>.py` | Tables 4.20 and 4.21, Figures 4.9 and 4.10; synthesis Tables 4.23 and 4.24 |
| `resultados_concorrencia_chromadb_http_<metric>.csv` | `escalabilidade_chromadb_http.py` | Table 4.22 |
| `diagnostico_concorrencia.csv` | `diagnostico_concorrencia.py` | Table 4.19 |

**`resultados_concorrencia_*.csv`** — one row per replica (3) and number of client processes (1, 2, 4, 8, 16, 24, 32): `Replica`, `Processos`, `QPS` (throughput, queries/s), `p50_ms`, `p95_ms`, `p99_ms` (latency percentiles, ms), `Repeticoes` (queries repeated after a connection error) and `Falhas` (queries that failed after 3 attempts).

**`diagnostico_concorrencia.csv`** — one row per load mode and number of clients (L2, one replica, 5,000 queries): `Motor`, `Cliente` (client library or `http`), `Geracao_carga` (`threads` or `processos`), `Clientes`, `QPS`, `p50_ms`, `p95_ms`, `Repeticoes`, `Falhas`, `Pct_repetidas`, `Pct_falhadas`.
