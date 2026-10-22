# Qdrant vs pgvector vs ChromaDB Benchmark

![Experimental Architecture](docs/architecture_diagram.png)
*(Note: Replace `docs/architecture_diagram.png` with the actual exported image of your Docker architecture from Figure 3.1 in the thesis)*

## Overview
This repository contains the experimental benchmarking code and data from the Master's thesis **"Análise Comparativa de SGBDV: Benchmark Experimental entre Qdrant, pgvector e ChromaDB"** (Francisco Caneira, IP Santarém, 2026). 

It evaluates the performance, resource efficiency (RAM/Disk), and operational trade-offs of three distinct Vector Database paradigms:
1. **Native Vector Engine:** Qdrant
2. **Relational Extension:** pgvector (PostgreSQL)
3. **Hybrid Wrapper Architecture:** ChromaDB

All tests are conducted using the **SIFT1M dataset** (1 million vectors, 128 dimensions) and the **HNSW algorithm**, evaluated across both **L2 Distance** and **Cosine Similarity**.

## Key Findings
* **Qdrant:** Offers the fastest indexing time and highest throughput (up to ~534 QPS at 1M scale). Best suited for strict latency SLAs, though it relies heavily on Page Cache for optimal performance.
* **pgvector:** Exceptionally memory-efficient (maintaining active RAM under 300MB during profiling) and robust under load. The ideal choice for existing SQL ecosystems with strict memory limits.
* **ChromaDB:** Achieves a balanced memory footprint but suffers from severe "cold start" latency (~1.7s) and structural throughput limits due to its Python/SQLite wrapper architecture.

## Prerequisites
To reproduce these experiments in isolated environments (as designed in the thesis), you will need:
* **OS:** Linux (Ubuntu Server 24.04 LTS recommended)
* **Docker Engine:** `docker-ce 29.3.0` or equivalent (with `cgroups v2` support for resource limiting)
* **Python:** Version 3.12+
* **Hardware Requirements:** At least 4 physical CPU cores and 16GB of RAM (Docker containers are strictly limited to 8GB RAM each via `mem_limit`).

## Setup and Installation

### 1. Start the Docker Containers
The repository includes configurations to run each database in total isolation. Swap must be disabled on the host to enforce strict memory limits.

```bash
# Start Qdrant
docker compose -f docker/qdrant-compose.yml up -d

# Start pgvector
docker compose -f docker/pgvector-compose.yml up -d

# Start ChromaDB
docker compose -f docker/chromadb-compose.yml up -d
```

### 2. Install Python Dependencies
Set up your virtual environment and install the required official clients and analysis libraries (e.g., `qdrant-client`, `psycopg2`, `chromadb`, `scipy`, `pandas`):

```bash
python3 -m venv vdb-env
source vdb-env/bin/activate
pip install -r requirements.txt
```

### 3. Download the Dataset
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