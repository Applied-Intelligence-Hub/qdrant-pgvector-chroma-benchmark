# Qdrant vs pgvector vs ChromaDB Benchmark

![Experimental Architecture](docs/architecture_diagram.png)

## Overview
This repository contains the experimental benchmarking code and data from the Master's thesis **"Análise Comparativa de SGBDV: Benchmark Experimental entre Qdrant, pgvector e ChromaDB"** (Francisco Caneira, IP Santarém, 2026). 

It evaluates the performance, resource efficiency (RAM/Disk), and operational trade-offs of three distinct Vector Database paradigms:
1. **Native Vector Engine:** Qdrant 1.9.4 (`qdrant-client` 1.9.2)
2. **Relational Extension:** pgvector 0.8.1 on PostgreSQL 16
3. **Hybrid Wrapper Architecture:** ChromaDB 1.5.5, a Rust server that combines the hnswlib index (C++) with SQLite for metadata (`chromadb` client 1.5.5)

All tests are conducted using the **SIFT1M dataset** (1 million vectors, 128 dimensions) and the **HNSW algorithm** with the same parameters in the three engines (`m=16`, `ef_construction=200`, `ef_search=64`), evaluated across both **L2 Distance** and **Cosine Similarity**.

Every number in this thesis comes from a CSV file in `results/`, produced by a script in `scripts/`. Script names, comments and terminal messages are in Portuguese, the language of the thesis.

## Key Findings
Results at the 1M-vector scale, for each metric (Tables 4.23 and 4.24 of the thesis). The best value of each row is in bold.

| | Qdrant | ChromaDB | pgvector |
|---|---:|---:|---:|
| Time until the collection is searchable (s) | **317.7** | 460.2 | 1,099.2 |
| Latency p50 (ms) | **2.02** | 2.45 | 4.34 |
| Latency p95 (ms) | **2.25** | 2.94 | 5.14 |
| Recall@10 (%) | **98.83** | 96.35 | 97.72 |
| Sequential throughput (QPS) | **493** | 398 | 241 |
| Maximum throughput under concurrency (QPS) | **1,448** | 676 | 533 |
| Batch insertion, 100,000 vectors (vec/s) | **5,797** | 4,435 | 3,029 |
| RAM: peak increase during indexing (MB) | 1,553 | **1,052** | 1,224 |
| RAM: increase at the end of indexing (MB) | 1,267 | 1,052 | **197** ¹ |
| Disk usage without WAL (MiB) | **384.9** | 795.5 | 1,361.6 |
| Cold start: container start to first answer (s) | 5.16 | 4.70 | **0.86** |
| Cold start: extra time over the 1,000 queries (s) | **0.02** | 5.08 | 10.88 |

**Cosine similarity**

| | Qdrant | ChromaDB | pgvector |
|---|---:|---:|---:|
| Time until the collection is searchable (s) | **297.5** | 456.4 | 1,168.1 |
| Latency p50 (ms) | **1.97** | 2.53 | 4.44 |
| Latency p95 (ms) | **2.21** | 2.96 | 5.26 |
| Recall@10 (%) | **98.82** | 96.36 | 97.72 |
| Sequential throughput (QPS) | **506** | 385 | 236 |
| Maximum throughput under concurrency (QPS) | **1,516** | 677 | 529 |
| Batch insertion, 100,000 vectors (vec/s) | **5,902** | 4,466 | 2,552 |
| RAM: peak increase during indexing (MB) | 1,396 | **1,041** | 1,225 |
| RAM: increase at the end of indexing (MB) | 1,236 | 1,041 | **197** ¹ |
| Disk usage without WAL (MiB) | **463.3** | 795.5 | 1,361.8 |
| Cold start: container start to first answer (s) | 5.82 | 4.70 | **0.88** |
| Cold start: extra time over the 1,000 queries (s) | **0.02** | 5.12

Medians of 10 replicas for the base benchmark (time until searchable, latency, recall and sequential throughput) and the cold start, and of 3 replicas for batch insertion and concurrency; one run for RAM profiling and disk usage (disk usage of Qdrant: three runs, the last one reported). The latency rows come from the base benchmark; the detailed latency experiment (5 replicas, Section 4.1.2) is not summarised here, because its higher p95 for Qdrant reflects a behaviour of the ´qdrant-client´ library, discussed in the thesis. MB and GB are binary units (2^20 and 2^30 bytes), as in the thesis. The choice of metric does not change the ranking of the engines in any row.

¹ pgvector serves queries from the operating system's page cache, which this measurement excludes: the value is the memory the process keeps, not the memory it needs to serve queries.

* **Qdrant:** Offers the fastest indexing time, the lowest latency, the highest throughput (about 500 QPS sequentially and 1,450 QPS under concurrency) and the lowest disk usage. The cost is memory: the highest peak during indexing, which stays at about 1.25 GiB afterwards. It is also the slowest engine to become available after a restart, because it loads the whole index at startup.
* **pgvector:** The fastest engine up to 100,000 vectors, but at 1M vectors it has the highest latency and the longest indexing time. It keeps the least memory after indexing (about 0.2 GiB) and answers first after a restart. This memory figure excludes the operating system's page cache, from which pgvector serves its queries (about 1.3 GiB for the table and the index). It was evaluated with PostgreSQL's default configuration.
* **ChromaDB:** Ranks between the other two engines on most dimensions, with the lowest memory peak during indexing but the lowest Recall@10. Its first query after a restart takes about 4 s, while it loads the index. Queried through direct HTTP requests, it reaches the same throughput plateau as through its client library, so the plateau comes from the server.

See Chapter 4 and the decision matrix in Chapter 5 of the thesis for the full analysis and [Limitations and Notes](#limitations-and-notes) below for the conditions under which these results are valid.

## Prerequisites
To reproduce these experiments in isolated environments (as designed in the thesis), you will need:
* **OS:** Linux (Ubuntu Server 24.04 LTS recommended)
* **Docker Engine:** `docker-ce 29.3.0` or equivalent (with `cgroups v2` support for resource limiting)
* **Python:** Version 3.12+
* **Hardware Requirements:** At least 4 physical CPU cores and 16GB of RAM (Docker containers are strictly limited to 8GB RAM each via `mem_limit`).

## Setup and Installation

### 1. Install Docker
```bash
sudo apt update
sudo apt install ca-certificates curl gnupg -y

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin -y

sudo usermod -aG docker $USER
newgrp docker
```
### 2. Start the Docker Containers
The repository includes configurations to run each database in total isolation. Swap must be disabled on the host to enforce strict memory limits.

```bash
# Start Qdrant
docker compose -f docker/qdrant-compose.yml up -d

# Start pgvector
docker compose -f docker/pgvector-compose.yml up -d

# Start ChromaDB
docker compose -f docker/chromadb-compose.yml up -d
```

### 3. Install Python Dependencies
Set up your virtual environment and install the required official clients and analysis libraries (e.g., `qdrant-client`, `psycopg2`, `chromadb`, `scipy`, `pandas`):

```bash
python3 -m venv vdb-env
source vdb-env/bin/activate
pip install -r requirements.txt
```

### 4. Download the Dataset
You need to download the **SIFT1M dataset** and place it in the `data/` directory.

```bash
mkdir data
# Download SIFT1M base vectors, query vectors, and ground truth files here
```

## How to Run the Benchmarks

The benchmark suite is entirely orchestrated using Python. Run the scripts sequentially from the terminal. 

### Step 1: Data Ingestion (Preparation)
Before running performance metrics, ingest the 1 million vectors into the respective engines.

```bash
python3 scripts/ram_inserir_qdrant.py
python3 scripts/ram_inserir_pgvector.py
python3 scripts/ram_inserir_chromadb.py
```

### Step 2: Base Performance Benchmarking
These scripts execute 10,000 queries to measure baseline Latency (p50, p95, p99), Throughput (QPS), and Recall@10.

```bash
python3 scripts/bench_qdrant.py
python3 scripts/bench_pgvector.py
python3 scripts/bench_chromadb.py
```

### Step 3: Parameter Optimization
To map the efficiency surfaces and find the Pareto optimal configurations for `m` and `ef_search` (maintaining `ef_construction=200`):

```bash
python3 scripts/otimizacao_qdrant.py
python3 scripts/otimizacao_pgvector.py
python3 scripts/otimizacao_chromadb.py
```

### Step 4: Complementary Scenarios
Test specific production scenarios like concurrency scaling, batch ingestion limits, and physical disk usage:

* **Concurrency Scaling (1 to 32 threads):** `python3 scripts/escalabilidade_qdrant.py`
* **Batch Ingestion:** `python3 scripts/lote_inserir_pgvector.py`
* **Cold Start vs. Warm Cache:** `python3 scripts/cold_warm_chromadb.py`
* **Disk Usage Analytics:** `python3 scripts/disco_qdrant.py`

### Step 5: Statistical Analysis
Once the CSV results are generated, run the statistical analysis script to calculate Welch's t-test, Mann-Whitney U, and Shapiro-Wilk validations across the runs:

```bash
python3 scripts/analise_estatistica.py
```

## Repository Structure

* `docker/`: Docker Compose files ensuring hardware parity (4 CPUs, 8GB RAM).
* `scripts/`: All Python orchestration scripts (Ingestion, Benchmarking, Profiling).
* `results/`: Output CSV files containing the raw telemetry and execution times.
* `docs/`: Supplementary documentation and architecture diagrams.

## Citation
If you use this benchmark data or methodology in your research, please refer to the original thesis:
> Caneira, F. D. M. M. (2026). *Análise Comparativa de SGBDV: Benchmark Experimental entre Qdrant, pgvector e ChromaDB.* IPSantarém.
