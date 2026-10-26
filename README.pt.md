# Benchmark Qdrant vs pgvector vs ChromaDB

[English](README.md) | **Português**

![Arquitetura experimental](docs/architecture_diagram.png)

## Visão geral
Este repositório contém o código e os dados experimentais da dissertação de Mestrado **"Análise Comparativa de SGBDV: Benchmark Experimental entre Qdrant, pgvector e ChromaDB"** (Francisco Caneira, IP Santarém, 2026).

Avalia o desempenho, a eficiência no uso de recursos (RAM e disco) e os *trade-offs* operacionais de três paradigmas de bases de dados vetoriais:
1. **Motor vetorial nativo:** Qdrant 1.9.4 (`qdrant-client` 1.9.2)
2. **Extensão relacional:** pgvector 0.8.1 sobre PostgreSQL 16
3. **Arquitetura híbrida (*wrapper*):** ChromaDB 1.5.5, um servidor em Rust que combina o índice do hnswlib (C++) com o SQLite para os metadados (cliente `chromadb` 1.5.5)

Todos os ensaios usam o **dataset SIFT1M** (1 milhão de vetores de 128 dimensões) e o **algoritmo HNSW**, com os mesmos parâmetros nos três motores (`m=16`, `ef_construction=200`, `ef_search=64`), nas métricas **Distância L2** e **Similaridade de Cosseno**.

Cada valor da tese vem de um ficheiro CSV em `results/`, produzido por um script em `scripts/`.

## Principais resultados
Resultados à escala de um milhão de vetores, para cada métrica (Tabelas 4.23 e 4.24 da tese). A negrito, o melhor valor de cada linha.

**Métrica L2**

| | Qdrant | ChromaDB | pgvector |
|---|---:|---:|---:|
| Tempo até a coleção estar pronta a pesquisar (s) | **317,7** | 460,2 | 1 099,2 |
| Latência p50 (ms) | **2,02** | 2,45 | 4,34 |
| Latência p95 (ms) | **2,25** | 2,94 | 5,14 |
| Recall@10 (%) | **98,83** | 96,35 | 97,72 |
| *Throughput* sequencial (QPS) | **493** | 398 | 241 |
| *Throughput* máximo sob concorrência (QPS) | **1 448** | 676 | 533 |
| Inserção em lote, 100 000 vetores (vec/s) | **5 797** | 4 435 | 3 029 |
| RAM: acréscimo máximo durante a indexação (MB) | 1 553 | **1 052** | 1 224 |
| RAM: acréscimo no fim da indexação (MB) | 1 267 | 1 052 | **197** ¹ |
| Disco sem o WAL (MiB) | **384,9** | 795,5 | 1 361,6 |
| Arranque a frio: do arranque do contentor à primeira resposta (s) | 5,16 | 4,70 | **0,86** |
| Arranque a frio: tempo adicional nas 1 000 consultas (s) | **0,02** | 5,08 | 10,88 |

**Similaridade de Cosseno**

| | Qdrant | ChromaDB | pgvector |
|---|---:|---:|---:|
| Tempo até a coleção estar pronta a pesquisar (s) | **297,5** | 456,4 | 1 168,1 |
| Latência p50 (ms) | **1,97** | 2,53 | 4,44 |
| Latência p95 (ms) | **2,21** | 2,96 | 5,26 |
| Recall@10 (%) | **98,82** | 96,36 | 97,72 |
| *Throughput* sequencial (QPS) | **506** | 385 | 236 |
| *Throughput* máximo sob concorrência (QPS) | **1 516** | 677 | 529 |
| Inserção em lote, 100 000 vetores (vec/s) | **5 902** | 4 466 | 2 552 |
| RAM: acréscimo máximo durante a indexação (MB) | 1 396 | **1 041** | 1 225 |
| RAM: acréscimo no fim da indexação (MB) | 1 236 | 1 041 | **197** ¹ |
| Disco sem o WAL (MiB) | **463,3** | 795,5 | 1 361,8 |
| Arranque a frio: do arranque do contentor à primeira resposta (s) | 5,82 | 4,70 | **0,88** |
| Arranque a frio: tempo adicional nas 1 000 consultas (s) | **0,02** | 5,12 | 10,85 |

Medianas de 10 réplicas no *benchmark* de base (tempo até a coleção estar pronta, latência, *recall* e *throughput* sequencial) e no arranque a frio, e de 3 réplicas na inserção em lote e na concorrência; uma execução no perfil de RAM e no disco (no disco do Qdrant, três medições, apresentando-se a última). As linhas de latência vêm do *benchmark* de base; o ensaio de latência detalhada (5 réplicas, Secção 4.1.2) não está resumido aqui, porque o seu p95 mais alto no Qdrant reflete um comportamento da biblioteca `qdrant-client`, discutido na tese. MB e GB são unidades binárias (2^20 e 2^30 bytes), como na tese. A escolha da métrica não altera a ordenação dos motores em nenhuma linha.

¹ O pgvector serve as consultas a partir da *cache* de ficheiros do sistema operativo, que esta medição exclui: o valor é a memória que o processo mantém, e não a de que precisa para servir as consultas.

* **Qdrant:** Tem o menor tempo de indexação, a menor latência, o maior *throughput* (cerca de 500 QPS em regime sequencial e 1 450 QPS sob concorrência) e o menor consumo de disco. O custo está na memória: o maior pico durante a indexação, que se mantém perto de 1,25 GiB depois dela. É também o motor mais lento a ficar disponível após um reinício, porque carrega o índice inteiro no arranque.
* **pgvector:** É o motor mais rápido até 100 000 vetores, mas, a um milhão de vetores, tem a maior latência e o maior tempo de indexação. É o que menos memória mantém depois da indexação (cerca de 0,2 GiB) e o que responde primeiro após um reinício. Este valor de memória exclui a *cache* de ficheiros do sistema operativo, a partir da qual o pgvector serve as consultas (cerca de 1,3 GiB para a tabela e o índice). Foi avaliado com a configuração por omissão do PostgreSQL.
* **ChromaDB:** Fica entre os outros dois motores na maioria das dimensões, com o menor pico de memória durante a indexação, mas o Recall@10 mais baixo. A primeira consulta após um reinício demora cerca de 4 s, enquanto carrega o índice. Consultado por pedidos HTTP diretos, atinge o mesmo patamar de *throughput* que através da biblioteca cliente, pelo que o patamar vem do servidor.

O Capítulo 4 e a matriz de decisão do Capítulo 5 da tese apresentam a análise completa, e a secção [Limitações e avisos](#limitações-e-avisos), mais abaixo, as condições em que estes resultados são válidos.

## Requisitos
Para reproduzir os ensaios em ambientes isolados (como na tese), é preciso:
* **Sistema operativo:** Linux (recomenda-se o Ubuntu Server 24.04 LTS)
* **Docker Engine:** `docker-ce 29.3.0` ou equivalente, com suporte para `cgroups v2` na limitação de recursos
* **Python:** versão 3.12
* ***Hardware*:** A tese usou um Intel Core i5-7400 (4 núcleos) com 16 GiB de RAM. Cada contentor está limitado a uma quota de 4 CPUs (`cpus: 4`) e a 8 GiB de RAM sem *swap* (`mem_limit` e `memswap_limit`). O cliente de *benchmark* corre no mesmo anfitrião e partilha os seus núcleos.
* **Modo de frequência do CPU:** Todos os ensaios finais usaram o modo `performance` (a configuração perde-se ao reiniciar a máquina):
  ```bash
  echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
  ```
* **`sudo` sem palavra-passe para limpar a *page cache***, usado pelos ensaios de monitorização da RAM e de arranque a frio (os scripts do arranque a frio param se não a conseguirem limpar). Abre o ficheiro sudoers com `sudo visudo` e acrescenta, substituindo `<utilizador>` pelo teu nome de utilizador:
  ```
  <utilizador> ALL=(ALL) NOPASSWD: /bin/sh -c echo 3 > /proc/sys/vm/drop_caches
  ```

## Instalação

### 1. Instalar o Docker
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

### 2. Iniciar os contentores
O repositório inclui a configuração de cada motor, tal como no Apêndice A da tese. Cada motor corre no seu próprio contentor, limitado a uma quota de 4 CPUs e a 8 GiB de RAM. Com o `memswap_limit` igual ao `mem_limit`, os contentores não podem usar *swap*: um contentor que exceda o limite de memória falha, em vez de passar a usar o disco. A quota de CPU não reserva núcleos: os contentores partilham os 4 núcleos do servidor com o sistema operativo e com o cliente de *benchmark*.

```bash
# Iniciar o Qdrant
docker compose -f docker/qdrant-compose.yml up -d

# Iniciar o pgvector
docker compose -f docker/pgvector-compose.yml up -d

# Iniciar o ChromaDB
docker compose -f docker/chromadb-compose.yml up -d
```

O Docker Compose dá a cada volume o nome `<pasta>_<volume>`, a partir da pasta onde estão os ficheiros do Compose, por isso estes comandos criam os volumes `docker_qdrant_data`, `docker_pgvector_data` e `docker_chromadb_data`. São os nomes usados pelo `monitorizar_ram.py` e pelos comandos abaixo; se mudares os ficheiros do Compose para outra pasta, confirma os nomes com `docker volume ls`.

Confirma que os serviços estão a correr e que os limites estão aplicados:

```bash
docker ps
docker inspect qdrant | grep -i memory
docker inspect pgvector | grep -i memory
docker inspect chromadb | grep -i memory
```

### 3. Criar o ambiente virtual Python
```bash
sudo apt install python3-venv python3-full -y
python3 -m venv ambiente-virtual
source ambiente-virtual/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Instala as bibliotecas cliente oficiais e as de análise (`qdrant-client`, `psycopg2`, `pgvector`, `chromadb`, `numpy`, `scipy`, `docker`, `tqdm`).

### 4. Descarregar e preparar o dataset SIFT1M
Descarrega o dataset do [corpus TEXMEX do INRIA](http://corpus-texmex.irisa.fr/) e prepara-o com quatro scripts, por esta ordem:

```bash
wget ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz
tar -xvzf sift.tar.gz                       # cria a pasta sift/ com os ficheiros .fvecs e .ivecs

python3 scripts/converter_sift.py             # .fvecs/.ivecs -> sift/sift_base.npy, sift_query.npy, sift_gt.npy
python3 scripts/gerar_subconjuntos.py         # os primeiros N vetores -> sift/subsets/sift_base_<N>.npy
python3 scripts/gerar_ground_truth_l2.py      # vizinhos exatos (L2) -> sift/gt/gt_<N>.npy
python3 scripts/gerar_ground_truth_cosseno.py # vizinhos exatos (Cosseno) -> sift/gt_cosine/gt_<N>.npy
```

Ou, de uma vez (transferência, extração, os quatro scripts e uma verificação final dos ficheiros):

```bash
python3 scripts/preparar_dados.py
```

Isto cria a estrutura que todos os scripts de ensaio esperam, a partir da raiz do repositório:

```
sift/sift_query.npy                  10 000 consultas
sift/subsets/sift_base_<N>.npy       os primeiros N vetores da base, N = 100, 1000, 10000, 100000, 1000000
sift/gt/gt_<N>.npy                   os 10 vizinhos mais próximos (L2) de cada consulta, em cada subconjunto
sift/gt_cosine/gt_<N>.npy            o mesmo para a Similaridade de Cosseno
```

Os subconjuntos são determinísticos (os primeiros N vetores). O SIFT1M só inclui o *ground truth* do conjunto completo em L2, por isso o `gerar_ground_truth_l2.py` (L2) e o `gerar_ground_truth_cosseno.py` (Cosseno) calculam o de cada subconjunto por pesquisa exata. O ficheiro [`docs/DATASET.md`](docs/DATASET.md) tem os pormenores. A pasta `sift/` não é versionada.

## Como executar os ensaios

Todos os ensaios são orquestrados em Python. Executa os scripts a partir da **raiz do repositório**. Cada script de ensaio aceita `--metric l2` ou `--metric cosine` e escreve os seus CSV na pasta atual; as versões finais desses ficheiros estão em `results/`.

Não existe um orquestrador central: cada script é executado individualmente, para cada motor e métrica, pela ordem abaixo. Antes de cada ensaio, confirma que os motores contêm apenas o que o ensaio espera. Para esvaziar o ChromaDB (cujo servidor não apaga os ficheiros do índice das coleções removidas):

```bash
docker stop chromadb && docker run --rm -v docker_chromadb_data:/volume busybox sh -c "rm -rf /volume/*" && docker start chromadb
```

### Passo 1: Inserção dos dados e monitorização da RAM
Insere o milhão de vetores em cada motor enquanto o `scripts/monitorizar_ram.py` regista a memória do contentor. O monitor reinicia o contentor, espera que o serviço responda, executa o script de inserção indicado em `--cmd` e lê o `docker stats` (cerca de 3 em 3 s) até ele terminar. A opção `--clean` esvazia antes o volume do contentor, para o registo partir de um estado limpo.

```bash
sync; sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'
python3 scripts/monitorizar_ram.py --container qdrant --output ram_qdrant_l2.csv --clean \
        --cmd "python3 scripts/ram_inserir_qdrant.py --metric l2"
```

Repete para o `pgvector` e o `chromadb`, e com `--metric cosine`. Os scripts de inserção criam também as coleções `disk_test_<métrica>`, usadas nos Passos 4, 7 e 8.

### Passo 2: *Benchmark* de base
10 réplicas em cinco escalas (de 100 a 1M vetores), com 10 000 consultas por escala, medindo o tempo de indexação, a latência (p50, p95, p99), o *throughput* (QPS), a RAM e o Recall@10. Cada réplica reinicia o contentor.

```bash
python3 scripts/benchmark_base_qdrant.py --metric l2
python3 scripts/benchmark_base_pgvector.py --metric l2
python3 scripts/benchmark_base_chromadb.py --metric l2
```

No Qdrant, a indexação é desativada durante a inserção e ativada no fim com um limiar de 1 KB, para o índice HNSW ser construído em todas as escalas (com o limiar por omissão, de 20 000 KB, as coleções até 100 000 vetores são pesquisadas de forma exaustiva).

### Passo 3: Otimização paramétrica
Mapeia as superfícies de eficiência e encontra as configurações ótimas de Pareto para `m` ∈ {16, 24, 32} e `ef_search` ∈ {64, 128, 256} (mantendo `ef_construction=200`). Cada configuração é medida uma vez, com 1 000 consultas.

```bash
python3 scripts/otimizacao_qdrant.py --metric l2
python3 scripts/otimizacao_pgvector.py --metric l2
python3 scripts/otimizacao_chromadb.py --metric l2
```

### Passo 4: Cenários complementares
Cada script existe para os três motores (`qdrant`, `pgvector` e `chromadb`):

* **Consumo de disco:** `python3 scripts/disco_qdrant.py --metric l2`. O `disco_chromadb.py` exige uma instância do ChromaDB vazia e regista também o tamanho de cada ficheiro do índice. O `disco_pgvector.py` tem de ser executado **depois** do Passo 1: recria as tabelas `disk_test_<métrica>` com identificadores a começar em 0, como nos ficheiros do *ground truth*.
* **Latência detalhada:** `python3 scripts/latencia_qdrant.py --metric l2` (5 réplicas × 10 000 consultas).
* **Inserção em lote:** `python3 scripts/lote_inserir_qdrant.py --metric l2` (100 000 vetores, lotes de 100 a 50 000, 3 réplicas).
* **Arranque a frio vs. *cache* quente:** `python3 scripts/arranque_frio_qdrant.py --metric l2` (10 réplicas). No Qdrant, mantém apenas a coleção medida, porque o Qdrant carrega todas as coleções no arranque.
* **Escalabilidade sob concorrência (1 a 32 processos cliente):** `python3 scripts/escalabilidade_qdrant.py --metric l2` (3 réplicas). O Qdrant é consultado por pedidos HTTP diretos, porque o `qdrant-client` 1.9.2 limitava o *throughput*; o `escalabilidade_chromadb_http.py` mede o ChromaDB da mesma forma.

### Passo 5: Diagnósticos
Os scripts de diagnóstico sustentam afirmações específicas da tese:

```bash
python3 scripts/diagnostico_qdrant.py --metric l2        # qdrant-client vs. HTTP direto vs. tempo no servidor
python3 scripts/diagnostico_pgvector.py --metric l2      # tempo no servidor do pgvector (EXPLAIN ANALYZE)
python3 scripts/diagnostico_serializacao_pgvector.py     # tamanho e tempo de preparação dos vetores enviados pelo pgvector
python3 scripts/diagnostico_concorrencia.py              # threads vs. processos, qdrant-client vs. HTTP
```

### Passo 6: Análise estatística e figuras
Depois de gerados os CSV, executa a análise estatística sobre os resultados do *benchmark* de base. Calcula as medianas das réplicas e compara os motores com o teste U de Mann-Whitney exato, com correção de Holm para comparações múltiplas, o delta de Cliff e o estimador de Hodges-Lehmann:

```bash
python3 scripts/analise_estatistica.py results/benchmark_base   # pasta com os seis results_*.csv
python3 scripts/gerar_figuras.py --dados results --saida figures
```

O `gerar_figuras.py` escreve o código LaTeX (pgfplots) das dez figuras do Capítulo 4, incluídas na tese com `\input{figures/<nome>.tex}`.

As Figuras 2.1 (pesquisa exata vs. aproximada) e 2.3 (distância euclidiana e similaridade de cosseno) são desenhadas com o Matplotlib e guardadas em `images/`:

```bash
python3 scripts/gerar_figura_pesquisa.py
python3 scripts/gerar_figura_metricas.py
```

## Limitações e avisos

### Limitações dos resultados
Estas limitações são discutidas na Secção 5.5 da tese, e definem as condições em que os resultados acima são válidos.

* **Âmbito da avaliação:** vetores de 128 dimensões (SIFT1M), até um milhão de vetores, um único servidor e cargas só de leitura. Os *embeddings* dos modelos de linguagem atuais têm entre 768 e 1 536 dimensões, onde o tamanho do índice, o custo das distâncias e o efeito da compressão mudam. Não foram avaliadas instalações distribuídas nem cargas mistas de leitura e escrita.
* **pgvector com a configuração por omissão do PostgreSQL:** os `shared_buffers` são de 128 MB, por isso a tabela e o índice (cerca de 1,3 GiB a um milhão de vetores) não cabem na *cache* do PostgreSQL. Os resultados do pgvector (tempo de indexação, latência a um milhão de vetores e arranque a frio) valem para esta configuração e podem mudar com afinação.
* **A latência inclui o cliente:** as latências são medidas no cliente Python e incluem a biblioteca cliente de cada motor e o transporte. O cliente de *benchmark* corre no mesmo servidor e partilha os 4 núcleos com os motores. O tempo no servidor foi medido no Qdrant e no pgvector (Secção 4.1.2), mas não no ChromaDB.
* **As bibliotecas cliente contam:** o `qdrant-client` 1.9.2 apresentou um nível de latência mais lento numa parte das consultas e limitou o *throughput* sob concorrência a pouco mais de metade do que o mesmo servidor atinge com pedidos HTTP diretos. Por isso, nos ensaios de concorrência, o Qdrant foi consultado por pedidos HTTP diretos, e o ChromaDB foi medido das duas formas.
* **A memória exclui a *page cache*:** os valores de RAM vêm do `docker stats` e das estatísticas do *cgroup*, que excluem a *cache* de ficheiros do sistema operativo. Isto favorece o pgvector, que serve as consultas a partir dela.
* **Execuções únicas:** o perfil de RAM, a otimização paramétrica e o consumo de disco são execuções únicas (no disco do Qdrant, três). As diferenças pequenas nestes ensaios, como escolhas da otimização separadas por 0,01 a 0,05 pontos percentuais de *recall*, devem ser lidas como indicativas.
* **Versões dos motores:** o Qdrant 1.9.4 (de 2024) é mais antigo do que as versões avaliadas do pgvector (0.8.1) e do ChromaDB (1.5.5). Versões posteriores do Qdrant e do seu cliente podem ter um desempenho diferente.
* **Duas campanhas:** os ensaios foram feitos em duas campanhas. Só a final (com o modo `performance` do processador e os protocolos corrigidos) está na tese e neste repositório.

### Avisos para quem for reproduzir os ensaios
Problemas encontrados ao longo dos ensaios, que afetam quem os repetir:

* **O ChromaDB não apaga os ficheiros do índice das coleções removidas.** Acumulam-se no volume (chegaram a várias dezenas de gigabytes durante a tese) e alteram as medições de disco e de memória. Esvazia o volume antes de cada ensaio (ver *Como executar os ensaios*).
* **O ChromaDB tem de ser reiniciado entre réplicas.** Sem reinício, a memória das coleções removidas não é libertada, e o valor em repouso vai subindo.
* **O Qdrant só indexa segmentos maiores do que o `indexing_threshold`** (20 000 KB por omissão, cerca de 40 000 vetores por segmento). Sem o alterar, as coleções até 100 000 vetores são pesquisadas de forma exaustiva, sem HNSW. Os scripts baixam o limiar para o índice ser sempre construído.
* **O Qdrant carrega todas as coleções no arranque.** No ensaio de arranque a frio, mantém só a coleção que estás a medir.
* **O pgvector precisa da classe de operadores da métrica** (`vector_l2_ops` ou `vector_cosine_ops`); caso contrário, o PostgreSQL ignora o índice HNSW e faz uma pesquisa sequencial. Os scripts confirmam o plano da consulta antes de medir.
* **No pgvector, os identificadores têm de começar em 0,** como nos ficheiros do *ground truth*. Corre o `disco_pgvector.py` depois dos scripts do perfil de RAM, que criam tabelas com identificadores a começar em 1.
* **No pgvector, a preparação dos vetores no cliente conta:** os vetores normalizados (Cosseno) geram um texto 3,6 vezes maior do que os valores inteiros do SIFT (L2), o que explica a maior parte da ingestão mais lenta em Cosseno (Secção 4.1.5).
* **Usa o modo `performance` do processador.** O *throughput* do ChromaDB com lotes de 100 vetores foi cerca de 40% mais alto com o `performance` do que com o `powersave` (1 734 contra 1 240 vec/s), a maior diferença observada entre os dois modos.
* **O tempo de arranque tem uma resolução de cerca de 0,1 s,** porque os scripts verificam a cada 0,1 s se o motor está pronto. Pela mesma razão, o tempo de índice de 0,41 s do Qdrant com 100 e 1 000 vetores não mede a construção do índice.
* **O nome dos volumes depende da pasta onde estão os ficheiros do Compose** (`<pasta>_<volume>`). Confirma-o com `docker volume ls` se os ficheiros do Compose estiverem noutra pasta que não `docker/`.

## Estrutura do repositório

* `docker/`: os ficheiros Docker Compose, que garantem a paridade de *hardware* (4 CPUs, 8 GiB de RAM).
* `scripts/`: todos os scripts Python (preparação do dataset, inserção, *benchmarking*, monitorização, diagnósticos, análise e figuras).
* `results/`: os CSV finais, numa pasta por ensaio (`benchmark_base`, `latency`, `ram_profiling`, `optimization`, `batch_insertion`, `cold_warm`, `disk`, `concurrency`). O ficheiro [`results/README.pt.md`](results/README.pt.md) explica cada coluna e a tabela ou figura da tese em que cada ficheiro é usado.
* `figures/`: o código LaTeX das figuras do Capítulo 4, gerado a partir de `results/`.
* `docs/`: as notas sobre a preparação do dataset e o diagrama da arquitetura.

## Citação
Se usares os dados ou a metodologia deste *benchmark*, cita a tese original:
> Caneira, F. D. M. M. (2026). *Análise Comparativa de SGBDV: Benchmark Experimental entre Qdrant, pgvector e ChromaDB.* IPSantarém.
