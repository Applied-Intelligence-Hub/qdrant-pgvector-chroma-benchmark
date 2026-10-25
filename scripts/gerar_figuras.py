r"""
Gera o código LaTeX (pgfplots) das 10 figuras do Capítulo 4 a partir dos CSV.

Cada figura fica num ficheiro .tex na pasta de saída e entra na tese com
\input{figures/<nome>.tex}. Os CSV podem estar na pasta indicada ou em subpastas.

  fig_latencia_distribuicao_*       latencias_<motor>_<metrica>.csv
  fig_profiling_memoria             ram_<motor>_<metrica>.csv
  fig_pareto_otimizacao             resultados_otimizacao_<motor>_<Metrica>.csv
  fig_batch_throughput_*            resultados_batch_<motor>_<Metrica>.csv
  fig_disco_*                       disk_<motor>_<metrica>.csv, disk_chromadb_ficheiros_indice_<metrica>.csv
  fig_throughput_concorrencia_*     resultados_concorrencia_<motor>_<metrica>.csv

Uso: python scripts/gerar_figuras.py --dados results --saida figures
"""
import argparse
import csv
import os
import statistics as st
from collections import defaultdict

import numpy as np

MOTORES = [("qdrant", "Qdrant"), ("chromadb", "ChromaDB"), ("pgvector", "pgvector")]
METRICAS = [("l2", "L2", r"\textbf{Métrica L2}"), ("cosine", "Cosine", r"\textbf{Similaridade de Cosseno}")]
MiB = 1024 ** 2


def localizar(dados, nome):
    """Procura o ficheiro na pasta indicada ou em qualquer subpasta (ex.: results/)."""
    for raiz, _, ficheiros in os.walk(dados):
        if nome in ficheiros:
            return os.path.join(raiz, nome)
    return None


def ler(dados, nome):
    caminho = localizar(dados, nome)
    if caminho is None:
        raise FileNotFoundError(f"{nome} não encontrado em {dados} nem nas subpastas")
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def escrever(saida, nome, conteudo):
    with open(os.path.join(saida, nome + ".tex"), "w", encoding="utf-8") as f:
        f.write(conteudo)


def virg(x, d):
    return f"{x:.{d}f}".replace(".", ",")


# latência
def fig_latencia(dados, saida):
    cores = {"qdrant": "blue", "chromadb": "green!60!black", "pgvector": "red"}
    centros = np.round(np.arange(1.45, 6.5, 0.1), 2)
    bordas = np.arange(1.4, 6.5001, 0.1)   # mesmas fronteiras usadas na tese
    for met, _, titulo in METRICAS:
        plots, fora = [], {}
        for m, nome in MOTORES:
            lat = np.array([float(r["Latency_ms"]) for r in ler(dados, f"latencias_{m}_{met}.csv")])
            cont, _ = np.histogram(lat, bins=bordas)
            freq = 100 * cont / len(lat)
            # consultas fora da janela visível do eixo (1,5 a 6,5 ms)
            abaixo, acima = 100 * np.mean(lat < 1.5), 100 * np.mean(lat >= 6.5)
            if abaixo + acima > 0:
                fora[nome] = (abaixo, acima)
            pts = " ".join(f"({c:.2f}, {v:.2f})" for c, v in zip(centros, freq))
            plots.append(f"\\addplot[color={cores[m]}, thick, mark=none] coordinates {{\n    {pts}\n}};\n\\addlegendentry{{{nome}}}")
        n = len(lat)
        eixo = "L2" if met == "l2" else "Cosseno"
        if fora:
            total = sum(a + b for a, b in fora.values())
            teto = np.ceil(total * 10) / 10                     # arredondado por excesso a 0,1
            quem = " e ".join(fora)
            lado = ("abaixo de 1,5~ms" if all(b == 0 for _, b in fora.values())
                    else "acima de 6,5~ms" if all(a == 0 for a, _ in fora.values()) else "fora de 1,5 a 6,5~ms")
            nota = f"Menos de {virg(teto, 1)}\\% das consultas, todas do {quem} e {lado}, ficam fora da janela representada."
        else:
            nota = "Todas as consultas ficam dentro da janela representada."
        escrever(saida, f"fig_latencia_distribuicao_{met}", r"""\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    width=0.95\textwidth, height=0.40\textwidth,
    xlabel={Latência """ + eixo + r""" (ms)}, ylabel={Frequência relativa (\%)},
    xmin=1.5, xmax=6.5, ymin=0,
    grid=major, grid style={dashed, gray!20},
    /pgf/number format/use comma,
    legend columns=3,
    legend style={at={(0.5,1.02)}, anchor=south, font=\small, draw=none, /tikz/column sep=6pt}
]
""" + "\n".join(plots) + r"""
\end{axis}
\end{tikzpicture}
\caption{Distribuição da latência para as consultas sequenciais sob a """ + titulo + r""", agregando as \num{""" + str(n) + r"""} consultas das 5 réplicas de cada motor (classes de 0,1~ms). """ + nota + r"""}
\label{fig:latencia_distribuicao_""" + met + r"""}
\end{figure}
""")


# RAM
def fig_ram(dados, saida):
    estilo = {"qdrant": ("blue", "solid"), "chromadb": ("green!60!black", "densely dotted"), "pgvector": ("red", "dashed")}

    def serie(m, met):
        s = [(float(r["Tempo_Segundos"]), float(r["RAM_MB"])) for r in ler(dados, f"ram_{m}_{met}.csv")]
        imax = max(range(len(s)), key=lambda i: s[i][1])
        idx = sorted(set(list(range(0, len(s), 5)) + [imax, len(s) - 1]))
        return " ".join(f"({s[i][0]:.0f},{s[i][1]:.0f})" for i in idx)

    def painel(met, legenda, ylabel):
        plots = ""
        for m, nome in MOTORES:
            c, e = estilo[m]
            plots += f"\\addplot[color={c}, {e}, thick, mark=none] coordinates {{\n    {serie(m, met)}\n}};\n\\addlegendentry{{{nome}}}\n"
        return r"""\begin{minipage}{0.49\textwidth}
\centering
\begin{tikzpicture}
\begin{axis}[
    width=\textwidth, height=0.85\textwidth,
    xlabel={Tempo (s)}, ylabel={""" + ylabel + r"""},
    xmin=0, xmax=1050, ymin=0, ymax=1700,
    /pgf/number format/1000 sep={\,},
    grid=major, grid style={dashed, gray!25},
    legend style={at={(0.88,0.05)}, anchor=south east, font=\scriptsize},
    tick label style={font=\scriptsize}, label style={font=\small}
]
""" + plots + r"""\end{axis}
\end{tikzpicture}
\caption*{""" + legenda + r"""}
\end{minipage}"""

    escrever(saida, "fig_profiling_memoria", r"""\begin{figure}[H]
\centering
""" + painel("l2", "(a) Métrica L2", "Consumo de RAM (MB)") + "%\n\\hfill\n" + painel("cosine", "(b) Similaridade de Cosseno", "") + r"""
\caption{Evolução do consumo de RAM de cada contentor durante a inserção de 1\,000\,000 de vetores e a construção do índice HNSW. Cada série começa com o contentor acabado de reiniciar e termina quando o índice está construído. Valores absolutos medidos pelo \texttt{docker stats}.}
\label{fig:profiling_memoria}
\end{figure}
""")


# otimização
def fig_pareto(dados, saida):
    estilo = {"qdrant": ("blue", "*"), "chromadb": ("green!60!black", "triangle*"), "pgvector": ("red", "square*")}

    def painel(Met, legenda, ylabel):
        plots, escolhas = "", []
        for m, nome in MOTORES:
            linhas = ler(dados, f"resultados_otimizacao_{m}_{Met}.csv")
            pts = [(int(r["m"]), int(r["ef_search"]), float(r["p50_ms"]), float(r["Recall_10"])) for r in linhas]
            pts.sort(key=lambda p: (p[0], p[1]))
            c, mk = estilo[m]
            plots += (f"\\addplot[only marks, color={c}, mark={mk}, mark size=1.8pt] coordinates {{"
                      + " ".join(f"({p[2]:.2f},{p[3]:.2f})" for p in pts) + f"}};\n\\addlegendentry{{{nome}}}\n")
            validos = [p for p in pts if p[2] <= 10]          # critério: p50 <= 10 ms
            esc = max(validos, key=lambda p: (round(p[3], 2), -p[2]))
            escolhas.append(f"({esc[2]:.2f},{esc[3]:.2f})")
        plots += "\\addplot[only marks, mark=o, mark size=4pt, black, thick] coordinates {" + " ".join(escolhas) + "};\n\\addlegendentry{Escolha}\n"
        return r"""\begin{minipage}{0.49\textwidth}
\centering
\begin{tikzpicture}
\begin{axis}[
    width=\textwidth, height=0.9\textwidth,
    xlabel={Latência p50 (ms)}, ylabel={""" + ylabel + r"""},
    xmin=0, xmax=20, ymin=95.5, ymax=100.2,
    /pgf/number format/use comma,
    grid=major, grid style={dashed, gray!25},
    legend style={at={(0.97,0.03)}, anchor=south east, font=\scriptsize},
    tick label style={font=\scriptsize}, label style={font=\small}
]
\draw[gray, dashed] (axis cs:10,95.5) -- (axis cs:10,100.2);
""" + plots + r"""\end{axis}
\end{tikzpicture}
\caption*{""" + legenda + r"""}
\end{minipage}"""

    escrever(saida, "fig_pareto_otimizacao", r"""\begin{figure}[H]
\centering
""" + painel("L2", "(a) Métrica L2", r"Recall@10 (\%)") + "%\n\\hfill\n" + painel("Cosine", "(b) Similaridade de Cosseno", "") + r"""
\caption{Compromisso entre \textit{Recall@10} e latência mediana nas nove configurações de cada motor. Os círculos assinalam a configuração escolhida pelo critério; a linha tracejada marca o limiar de \SI{10}{\milli\second}.}
\label{fig:pareto_otimizacao}
\end{figure}
""")


# lote
def fig_lote(dados, saida):
    estilo = {"qdrant": ("blue", "*"), "chromadb": ("green!70!black", "triangle*"), "pgvector": ("red", "square*")}
    for met, Met, titulo in METRICAS:
        plots = ""
        for m, nome in MOTORES:
            g = defaultdict(list)
            for r in ler(dados, f"resultados_batch_{m}_{Met}.csv"):
                g[int(r["Batch_Size"])].append(float(r["Total_s"]))
            pts = " ".join(f"({b}, {round(100000 / st.median(v))})" for b, v in sorted(g.items()))
            c, mk = estilo[m]
            plots += f"\\addplot[color={c}, mark={mk}] coordinates {{\n    {pts}\n}};\n\\addlegendentry{{{nome}}}\n"
        escrever(saida, f"fig_batch_throughput_{met}", r"""\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    width=0.85\textwidth,
    height=0.42\textwidth,
    xlabel={Tamanho do lote},
    ylabel={Débito (vec/s)},
    xmode=log,
    log basis x={10},
    xmin=50, xmax=100000,
    ymin=0, ymax=7000,
    legend columns=3,
    legend style={at={(0.5,1.03)}, anchor=south, font=\small, draw=none, /tikz/column sep=6pt},
    /pgf/number format/1000 sep={\,},
    grid=major,
    grid style={dashed, gray!25},
    thick,
    mark options={solid}
]
""" + plots + r"""\end{axis}
\end{tikzpicture}
\caption{Débito de inserção em lote para a """ + titulo + r""", medido até a coleção estar pronta a pesquisar (mediana de 3 réplicas). Nos lotes acima de \num{10000} (Qdrant) e de \num{5461} (ChromaDB), os vetores são enviados em pedidos de tamanho máximo.}
\label{fig:batch_throughput_""" + met + r"""}
\end{figure}
""")


# disco
def decomposicao_chromadb(dados, met):
    """Vetores, grafo e identificadores do índice do ChromaDB, em MiB, a partir dos
    tamanhos dos ficheiros do hnswlib registados pelo disco_chromadb.py."""
    nome = f"disk_chromadb_ficheiros_indice_{met}.csv"
    if localizar(dados, nome) is None:
        nome = "disk_chromadb_ficheiros_indice.csv"
    f = {r["Ficheiro"]: int(r["Bytes"]) for r in ler(dados, nome)}
    n = f["data_level0.bin"] // (512 + 132 + 8)
    vetores = 512 * n
    grafo = 132 * n + f["link_lists.bin"] + f["length.bin"] + f["header.bin"]
    ids = 8 * n + f["index_metadata.pickle"]
    return vetores / MiB, grafo / MiB, ids / MiB


def fig_disco(dados, saida):
    for met, _, titulo in METRICAS:
        cv, cg, ci = decomposicao_chromadb(dados, met)
        q = ler(dados, f"disk_qdrant_{met}.csv")[0]
        c = ler(dados, f"disk_chromadb_{met}.csv")[0]
        p = ler(dados, f"disk_pgvector_{met}.csv")[0]
        vet = {"Qdrant": float(q["Vetores_RocksDB_MB"]), "ChromaDB": cv, "pgvector": float(p["Tabela_MB"])}
        ind = {"Qdrant": float(q["Grafo_HNSW_MB"]), "ChromaDB": cg, "pgvector": float(p["HNSW_MB"])}
        out = {"Qdrant": float(q["Restante_segmentos_MB"]) + float(q["Outros_MB"]),
               "ChromaDB": ci + float(c["SQLite_MB"]) + float(c["Outros_MB"]),
               "pgvector": float(p["Chave_primaria_MB"]) + float(p["TOAST_MB"]) + float(p["Outros_MB"])}
        linha = lambda d: " ".join(f"({k},{d[k]:.2f})" for k in ["Qdrant", "ChromaDB", "pgvector"])
        escrever(saida, f"fig_disco_{met}", r"""\begin{figure}[H]
\centering
\begin{tikzpicture}
\begin{axis}[
    ybar stacked, bar width=28pt,
    width=0.75\textwidth, height=0.45\textwidth,
    ylabel={Disco (MiB)}, ymin=0, ymax=1500,
    symbolic x coords={Qdrant,ChromaDB,pgvector}, xtick=data,
    /pgf/number format/1000 sep={\,},
    legend style={at={(0.02,0.98)}, anchor=north west, font=\small},
    grid=major, grid style={dashed, gray!25}
]
\addplot[fill=blue!55] coordinates {""" + linha(vet) + r"""};
\addplot[fill=orange!70] coordinates {""" + linha(ind) + r"""};
\addplot[fill=gray!50] coordinates {""" + linha(out) + r"""};
\legend{Vetores, Índice HNSW, Metadados e outros}
\end{axis}
\end{tikzpicture}
\caption{Decomposição do consumo de disco sob a """ + titulo + r""", sem o WAL.}
\label{fig:disco_""" + met + r"""}
\end{figure}
""")


# concorrência
def fig_concorrencia(dados, saida):
    estilo = {"qdrant": ("blue", "*"), "chromadb": ("green!60!black", "triangle*"), "pgvector": ("red", "square*")}
    P = [1, 2, 4, 8, 16, 24, 32]
    eixos = r"""    xmode=log, log basis x={2}, xtick={1,2,4,8,16,32}, xticklabels={1,2,4,8,16,32},
"""
    for met, _, titulo in METRICAS:
        a = b = ""
        for m, nome in MOTORES:
            g = defaultdict(list)
            for r in ler(dados, f"resultados_concorrencia_{m}_{met}.csv"):
                g[int(r["Processos"])].append(r)
            med = lambda n, col: st.median(float(x[col]) for x in g[n])
            c, mk = estilo[m]
            a += (f"\\addplot[color={c}, mark={mk}, thick] coordinates {{"
                  + " ".join(f"({n},{med(n, 'QPS'):.2f})" for n in P) + f"}};\n\\addlegendentry{{{nome}}}\n")
            b += (f"\\addplot[color={c}, mark={mk}, thick, forget plot] coordinates {{"
                  + " ".join(f"({n},{med(n, 'p95_ms'):.2f})" for n in P) + "};\n")
            b += (f"\\addplot[color={c}, mark={mk}, mark options={{solid, fill=white}}, thick, dashed, forget plot] coordinates {{"
                  + " ".join(f"({n},{med(n, 'p99_ms'):.2f})" for n in P) + "};\n")
        b += "\\addlegendimage{black, thick}\\addlegendentry{p95}\n\\addlegendimage{black, thick, dashed}\\addlegendentry{p99}\n"
        escrever(saida, f"fig_throughput_concorrencia_{met}", r"""\begin{figure}[H]
\centering
\begin{minipage}[b]{0.49\textwidth}
\centering
\begin{tikzpicture}
\begin{axis}[
    width=\textwidth, height=0.85\textwidth,
    xlabel={Processos cliente}, ylabel={\textit{Throughput} (QPS)},
""" + eixos + r"""    ymin=0,
    /pgf/number format/1000 sep={\,},
    grid=major, grid style={dashed, gray!25},
    legend columns=3, legend style={at={(0.5,1.03)}, anchor=south, font=\scriptsize, draw=none, /tikz/column sep=3pt},
    tick label style={font=\scriptsize}, label style={font=\small}
]
""" + a + r"""\end{axis}
\end{tikzpicture}
\caption*{(a) \textit{Throughput}}
\end{minipage}%
\hfill
\begin{minipage}[b]{0.49\textwidth}
\centering
\begin{tikzpicture}
\begin{axis}[
    width=\textwidth, height=0.85\textwidth,
    xlabel={Processos cliente}, ylabel={Latência (ms)},
""" + eixos + r"""    ymode=log, log basis y={10},
    /pgf/number format/1000 sep={\,},
    grid=major, grid style={dashed, gray!25},
    legend columns=2, legend style={at={(0.5,1.03)}, anchor=south, font=\scriptsize, draw=none, /tikz/column sep=4pt},
    tick label style={font=\scriptsize}, label style={font=\small}
]
""" + b + r"""\end{axis}
\end{tikzpicture}
\caption*{(b) Latências p95 e p99}
\end{minipage}
\caption{\textit{Throughput} e latências p95 e p99 sob concorrência crescente para a """ + titulo + r""" (mediana de 3 réplicas). No painel (b), cada motor mantém a cor do painel (a); a linha contínua corresponde ao p95 e a tracejada ao p99, em escala logarítmica.}
\label{fig:throughput_concorrencia_""" + met + r"""}
\end{figure}
""")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dados", default=".", help="Pasta com os CSV finais (por omissão, a pasta atual)")
    p.add_argument("--saida", default="figuras", help="Pasta onde escrever os ficheiros .tex (por omissão, figuras/)")
    a, _ = p.parse_known_args()   # ignora argumentos acrescentados pelo Jupyter/VS Code
    os.makedirs(a.saida, exist_ok=True)
    for f in (fig_latencia, fig_ram, fig_pareto, fig_lote, fig_disco, fig_concorrencia):
        f(a.dados, a.saida)
    print(f"10 figuras escritas em {a.saida}/:")
    for n in sorted(os.listdir(a.saida)):
        print("  ", n)
