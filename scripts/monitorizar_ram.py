r"""
Regista a RAM de um contentor enquanto corre um comando.

Reinicia o contentor, espera que o serviço responda, corre o comando de --cmd e
lê o docker stats até ele terminar (uma leitura a cada ~3 s). Com --clean apaga
antes o volume do contentor. Os nomes dos volumes em CONFIG são os que o Docker
Compose cria a partir da pasta docker/ (confirmar com docker volume ls).

Uso:
  python3 scripts/monitorizar_ram.py --container qdrant --output ram_qdrant_l2.csv --clean \
          --cmd "python3 scripts/ram_inserir_qdrant.py --metric l2"
"""
import time
import csv
import subprocess
import argparse
import requests

parser = argparse.ArgumentParser()

parser.add_argument("--container", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--cmd", required=False)
parser.add_argument("--clean", action="store_true",
                    help="Limpar os dados persistentes antes do benchmark")
args = parser.parse_args()


# Configuração de cada container

CONFIG = {
    "qdrant": {
        "volume": "docker_qdrant_data",
        "url": "http://localhost:6333/readyz"
    },
    "chromadb": {
        "volume": "docker_chromadb_data",
        "url": "http://localhost:8000/api/v2/heartbeat"
    },
    "pgvector": {
        "volume": "docker_pgvector_data",
        "url": None
    }
}

#Extrai o uso atual de memória do contentor que queremos via 'docker stats'.
#Normaliza as diferentes unidades devolvidas pelo docker, neste caso GB, para MB
def get_ram_mb(container):

    try:

        result = subprocess.run(
            ["docker","stats","--no-stream","--format","{{.MemUsage}}",container],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return 0

        mem = result.stdout.split("/")[0].strip()

        if "GiB" in mem:
            return float(mem.replace("GiB",""))*1024

        if "MiB" in mem:
            return float(mem.replace("MiB",""))

        if "GB" in mem:
            return float(mem.replace("GB",""))*1024

        if "MB" in mem:
            return float(mem.replace("MB",""))

    except:
        pass

    return 0


# Reiniciar contentor


print(f"\nA reiniciar '{args.container}'...")

subprocess.run(["docker","restart",args.container])


# Limpar volume (opcional)


if args.clean:

    print("A limpar volume Docker...")

    subprocess.run(["docker","stop",args.container])

    volume = CONFIG[args.container]["volume"]

    subprocess.run([
        "docker","run","--rm",
        "-v",f"{volume}:/volume",
        "busybox",
        "sh","-c","rm -rf /volume/*"
    ])

    subprocess.run(["docker","start",args.container])

#Esperar pelo serviço


url = CONFIG[args.container]["url"]

if url is not None:

    print("A aguardar que o serviço fique operacional...")

    while True:

        try:

            r = requests.get(url,timeout=2)

            if r.status_code == 200:
                break

        except:
            pass

        time.sleep(1)

print("Servidor pronto.")

print("A estabilizar memória...")
# Esperamos à volta de 5 segundos para garantir que os processos internos de um determinado motor
#e a sua alocação de memória no SO estabilize antes de iniciar outro benchmark
time.sleep(5)

print("Início da monitorização.\n")


# Lançar benchmark


processo = None

if args.cmd:

    print(args.cmd)

    processo = subprocess.Popen(args.cmd,shell=True)

start = time.time()

with open(args.output,"w",newline="") as f:

    writer = csv.writer(f)

    writer.writerow(["Tempo_Segundos","RAM_MB"])

    while True:

        t = int(time.time()-start)

        ram = get_ram_mb(args.container)

        writer.writerow([t,round(ram,2)])

        f.flush()

        print(f"[{t:4d}s] {ram:8.2f} MB")

        if processo is not None and processo.poll() is not None:
            print("\nBenchmark terminado.")
            break

        time.sleep(2)

print(f"\nRAM final: {ram:.2f} MB")
