# Resultados: dicionário de dados

[English](README.md) | **Português**

Ficheiros CSV finais da tese, numa pasta por ensaio. Todos os valores do Capítulo 4 vêm destes ficheiros.
Os nomes dos ficheiros e das colunas estão em português ou em inglês, tal como os scripts os escrevem; esta página explica cada coluna e a sua unidade.

Convenções: `<motor>` é `qdrant`, `chromadb` ou `pgvector`; `<métrica>` é `l2` ou `cosine` (`L2` ou `Cosine` nalguns nomes de ficheiros).
MB e GB são unidades binárias (2^20 e 2^30 bytes); os tamanhos em disco estão em MiB. Separador decimal: ponto.

---

## `benchmark_base/` — *Benchmark* de base (Secção 4.1.1)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `results_<motor>_<métrica>.csv` | `benchmark_base_<motor>.py` | Origem das medianas e dos testes abaixo |
| `medianas_base_<métrica>.csv` | `analise_estatistica.py` | Tabelas 4.1 e 4.2; Tabelas de síntese 4.23 e 4.24 |
| `testes_base.csv` | `analise_estatistica.py` | Tabelas 4.3 e 4.4 |

**`results_<motor>_<métrica>.csv`** — uma linha por réplica (10) e escala (de 100 a 1 000 000 vetores):

| Coluna | Significado | Unidade |
|---|---|---|
| `Replicate` | Número da réplica | — |
| `Scale` | Número de vetores na coleção | vetores |
| `Ingest_Time_s` | Tempo de envio dos vetores | s |
| `Index_Build_s` | Tempo de construção do índice HNSW depois da inserção (vazio no ChromaDB, que atualiza o índice durante a inserção) | s |
| `Ready_Time_s` | Tempo até a coleção estar pronta a pesquisar (inserção + índice) | s |
| `RAM_Baseline_GB` | Memória do contentor em repouso, antes da inserção | GB |
| `RAM_Build_Peak_GB` | Pico de memória durante a inserção e a construção do índice, acima do repouso | GB |
| `RAM_Query_Avg_GB` | Memória média durante as consultas, acima do repouso | GB |
| `p50_ms`, `p95_ms`, `p99_ms` | Percentis da latência das 10 000 consultas | ms |
| `QPS` | *Throughput* sequencial | consultas/s |
| `Recall@10` | Fração dos 10 vizinhos verdadeiros devolvidos | 0–1 |

**`medianas_base_<métrica>.csv`** — as mesmas colunas, com a mediana das 10 réplicas por motor (`Motor`) e escala.

**`testes_base.csv`** — uma linha por métrica, escala, par de motores e estatística:

| Coluna | Significado |
|---|---|
| `Metrica`, `Scale` | Métrica e escala |
| `Par` | Par comparado, na forma "A vs B" |
| `Estatistica` | Estatística comparada nas 10 réplicas (`p50_ms` ou `p95_ms`) |
| `Mediana_A`, `Mediana_B` | Mediana das 10 réplicas de cada motor (ms) |
| `U`, `p` | Estatística U do teste de Mann-Whitney exato e o respetivo valor-p bilateral |
| `p_Holm` | Valor-p depois da correção de Holm sobre os 60 testes |
| `Cliff_delta` | Delta de Cliff (tamanho do efeito, de −1 a 1; negativo significa que A é mais rápido) |
| `HL_ms` | Estimativa de Hodges-Lehmann da diferença A − B (ms) |
| `Mais_rapido` | Motor com a mediana mais baixa |

---

## `latency/` — Latência detalhada e diagnósticos (Secção 4.1.2)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `latencias_<motor>_<métrica>.csv` | `latencia_<motor>.py` | Figuras 4.1 e 4.2 |
| `latencias_<motor>_<métrica>_resumo.csv` | `latencia_<motor>.py` | Tabelas 4.5 e 4.6 |
| `diagnostico_qdrant_<métrica>.csv` | `diagnostico_qdrant.py` | Tabela 4.7 |
| `diagnostico_pgvector_<métrica>.csv` | `diagnostico_pgvector.py` | Tabela 4.8 |

| Ficheiro | Colunas |
|---|---|
| `latencias_*.csv` | `Replica` (1–5), `Query_ID` (0–9 999), `Latency_ms` (latência de cada consulta, medida no cliente) |
| `latencias_*_resumo.csv` | `Motor`, `Metrica`, `Replica`, os percentis de `p10` a `p99_9` e o `Max` (ms), e a `Skewness` (assimetria) e a `Kurtosis` (curtose) da distribuição de cada réplica |
| `diagnostico_qdrant_*.csv` | `Replica`, `Query_ID`, `Cliente_ms` (latência de um pedido HTTP direto, no cliente), `Servidor_ms` (tempo de pesquisa indicado pelo Qdrant na resposta) |
| `diagnostico_pgvector_*.csv` | `Consulta` (número da consulta), `Cliente_ms` (latência no cliente), `Planeamento_ms` e `Execucao_ms` (tempo de planeamento e de execução no PostgreSQL, obtido com `EXPLAIN ANALYZE`) |

---

## `ram_profiling/` — Perfil de RAM (Secção 4.1.3)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `ram_<motor>_<métrica>.csv` | `monitorizar_ram.py` com `ram_inserir_<motor>.py` | Figura 4.3, Tabelas 4.9 e 4.10 |

Colunas: `Tempo_Segundos` (tempo desde o início do registo, s) e `RAM_MB` (memória do contentor indicada pelo `docker stats`, ou seja, a memória total menos a *cache* de ficheiros inativa, MB). A primeira linha é o valor em repouso; os acréscimos indicados na tese são calculados em relação a ela.

---

## `optimization/` — Otimização paramétrica (Secção 4.1.4)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `resultados_otimizacao_<motor>_<Métrica>.csv` | `otimizacao_<motor>.py` | Tabelas 4.11 e 4.12, Figura 4.4 |

| Coluna | Significado | Unidade |
|---|---|---|
| `DB`, `Metric` | Motor e métrica | — |
| `m`, `ef_search` | Parâmetros do HNSW testados (`ef_construction` = 200) | — |
| `Recall_10` | *Recall@10* em 1 000 consultas | % |
| `p50_ms` | Latência mediana nas mesmas consultas | ms |
| `Total_GB` | Memória total do contentor | GB |
| `Anon_GB` | Memória anónima (reservada pelo processo) | GB |
| `File_GB` | *Cache* de ficheiros atribuída ao contentor | GB |
| `Shmem_GB` | Memória partilhada (os `shared_buffers` do PostgreSQL) | GB |

A "memória própria" das tabelas da tese é a `Anon_GB` (mais a `Shmem_GB`, no pgvector).

---

## `batch_insertion/` — Inserção em lote (Secção 4.1.5)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `resultados_batch_<motor>_<Métrica>.csv` | `lote_inserir_<motor>.py` | Tabelas 4.13 e 4.14, Figuras 4.5 e 4.6 |
| `diagnostico_serializacao_pgvector.csv` | `diagnostico_serializacao_pgvector.py` | Texto da Secção 4.1.5 |

**`resultados_batch_*.csv`** — uma linha por tamanho de lote e réplica (3):

| Coluna | Significado | Unidade |
|---|---|---|
| `Batch_Size` | Tamanho de lote pedido | vetores |
| `Pedido_efetivo` | Tamanho de cada pedido efetivamente enviado (limitado no Qdrant e no ChromaDB) | vetores |
| `Replica` | Número da réplica | — |
| `Ingestao_s` | Tempo de envio dos 100 000 vetores | s |
| `Indexacao_s` | Tempo de construção do índice (Qdrant e pgvector) | s |
| `Primeira_consulta_s` | Tempo de uma primeira consulta depois da inserção (ChromaDB, para garantir que a coleção já está pesquisável) | s |
| `Total_s` | Tempo até a coleção estar pronta a pesquisar | s |
| `Throughput_vec_s` | 100 000 / `Total_s` | vetores/s |

**`diagnostico_serializacao_pgvector.csv`** — `Metrica`, `Bytes_total` e `Bytes_por_vetor` (tamanho do texto SQL preparado pelo `psycopg2` para os 100 000 vetores, em bytes), `Preparacao_cliente_s` (tempo de preparação desse texto no cliente, s).

---

## `cold_warm/` — Arranque a frio vs. *cache* quente (Secção 4.1.6)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `resultados_cold_warm_<motor>_<Métrica>.csv` | `arranque_frio_<motor>.py` | Tabelas 4.15 e 4.16; Tabelas de síntese 4.23 e 4.24 |

Uma linha por réplica (10):

| Coluna | Significado | Unidade |
|---|---|---|
| `Arranque_s` | Do arranque do contentor até o motor e a coleção estarem disponíveis (verificado a cada 0,1 s) | s |
| `First_Resp_Cold_ms`, `First_Resp_Warm_ms` | Latência da primeira consulta da fase a frio e da fase quente | ms |
| `Cold_First10_Mean_ms` | Latência média das 10 primeiras consultas a frio | ms |
| `p50_Cold_ms`, `p95_Cold_ms`, `p50_Warm_ms`, `p95_Warm_ms` | Percentis da latência das 1 000 consultas de cada fase | ms |
| `Recall_Cold`, `Recall_Warm` | *Recall@10* de cada fase | % |
| `Excesso_Frio_s` | Tempo adicional da fase a frio face à fase quente: soma das 1 000 latências a frio menos a soma das 1 000 latências a quente (0 se for negativo) | s |

Nas Tabelas de síntese, o "arranque do contentor até à primeira resposta" é a mediana, entre as réplicas, de `Arranque_s` + `First_Resp_Cold_ms` / 1000.

---

## `disk/` — Consumo de disco (Secção 4.1.7)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `disk_<motor>_<métrica>.csv` | `disco_<motor>.py` | Tabelas 4.17 e 4.18, Figuras 4.7 e 4.8 |
| `disk_chromadb_ficheiros_indice_<métrica>.csv` | `disco_chromadb.py` | Divisão do índice do ChromaDB nas Figuras 4.7 e 4.8 |

Todos os tamanhos em MiB.

| Motor | Colunas |
|---|---|
| Qdrant | `Segments_MB` (pastas de segmento), `Vetores_RocksDB_MB` (vetores, na base RocksDB comprimida), `Grafo_HNSW_MB` (grafo HNSW), `Restante_segmentos_MB`, `WAL_MB`, `Outros_MB`, `Total_MB`, `Total_sem_WAL_MB`, `Vetores_brutos_MB` (tamanho dos vetores em bruto, 488 MiB), `Rácio_compressão`, `Espera_indexacao_s` (tempo de espera até o índice estar completo, antes de medir, s) |
| ChromaDB | `Indice_HNSW_MB` (pastas do índice do hnswlib), `SQLite_MB`, `WAL_MB` (registo de escrita do SQLite), `Outros_MB`, `Total_MB`, `Total_sem_WAL_MB`, `Vetores_brutos_MB` |
| pgvector | `Tabela_MB`, `HNSW_MB`, `Chave_primaria_MB`, `TOAST_MB`, `Outros_MB`, `Total_MB` (obtido com `pg_total_relation_size`), `WAL_cluster_MB` (WAL de todo o *cluster*, não incluído no total) |

O `disk_chromadb_ficheiros_indice_*.csv` indica o tamanho em bytes (`Bytes`) de cada ficheiro do hnswlib (`Ficheiro`): `data_level0.bin`, `link_lists.bin`, `length.bin`, `header.bin` e `index_metadata.pickle`.

---

## `concurrency/` — Concorrência (Secção 4.1.8)

| Ficheiro | Produzido por | Usado em |
|---|---|---|
| `resultados_concorrencia_<motor>_<métrica>.csv` | `escalabilidade_<motor>.py` | Tabelas 4.20 e 4.21, Figuras 4.9 e 4.10; Tabelas de síntese 4.23 e 4.24 |
| `resultados_concorrencia_chromadb_http_<métrica>.csv` | `escalabilidade_chromadb_http.py` | Tabela 4.22 |
| `diagnostico_concorrencia.csv` | `diagnostico_concorrencia.py` | Tabela 4.19 |

**`resultados_concorrencia_*.csv`** — uma linha por réplica (3) e número de processos cliente (1, 2, 4, 8, 16, 24, 32): `Replica`, `Processos`, `QPS` (*throughput*, consultas/s), `p50_ms`, `p95_ms`, `p99_ms` (percentis da latência, ms), `Repeticoes` (consultas repetidas depois de um erro de ligação) e `Falhas` (consultas que falharam depois de 3 tentativas).

**`diagnostico_concorrencia.csv`** — uma linha por modo de geração da carga e número de clientes (L2, uma réplica, 5 000 consultas): `Motor`, `Cliente` (biblioteca cliente ou `http`), `Geracao_carga` (`threads` ou `processos`), `Clientes`, `QPS`, `p50_ms`, `p95_ms`, `Repeticoes`, `Falhas`, `Pct_repetidas`, `Pct_falhadas`.
