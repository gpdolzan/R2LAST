import socket
import struct
import logging
import subprocess
import re
import os
import time
import sys
from datetime import datetime
from moviepy.editor import VideoFileClip

# Configuração do servidor
VIDEO_FOLDER = "video"
MULTICAST_IP = '224.0.0.1'
MULTICAST_PORT = 5004
CHUNK_SIZE = 1468 # Tamanho do pacote menos 4 bytes para o contador
PACKET_INTERVAL_MAP = {}  # Mapa para armazenar o intervalo de tempo entre pacotes para cada vídeo
PACKETS_SENT = 0
INTERVAL_TIME = None

# Configuração do logging
log_filename = datetime.now().strftime("servidor_%H%M%S.txt")
logging.basicConfig(filename=log_filename,
                    filemode='w',
                    level=logging.DEBUG,
                    format='SERVER - %(asctime)s - %(levelname)s - %(message)s')

# Verificar se o INTERVAL_TIME foi passado como argumento na linha de comando
if len(sys.argv) > 1:
    try:
        INTERVAL_TIME = float(sys.argv[1])
        logging.info(f"Intervalo de transmissão de pacote definido pela linha de comando: {INTERVAL_TIME} segundos.")
    except ValueError:
        logging.error("O valor do INTERVAL_TIME passado não é um número válido. Usando valores pré-calculados.")

# Criação do socket de datagrama
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
logging.info("Socket criado.")

# Definir o tempo de vida das mensagens para 1 para que não ultrapassem o segmento de rede local.
ttl = struct.pack('b', 1)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
logging.info("Tempo de vida das mensagens definido para 1.")

# Função para listar todos os arquivos de vídeo em um diretório
def list_video_files(directory):
    return [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

# Função para calcular o intervalo de tempo entre pacotes de um vídeo
def calculate_packet_interval(bitrate):
    return (CHUNK_SIZE * 8) / bitrate  # converte CHUNK_SIZE para bits

# Função para listar todos os arquivos de vídeo em um diretório e calcular o intervalo de pacotes
def prepare_video_files(directory):
    for f in os.listdir(directory):
        full_path = os.path.join(directory, f)
        if INTERVAL_TIME is not None:
            PACKET_INTERVAL_MAP[full_path] = INTERVAL_TIME
            logging.info(f"Preparado '{full_path}' com intervalo de pacote {INTERVAL_TIME} segundos.")
        elif os.path.isfile(full_path):
            bitrate = get_video_bitrate(full_path)
            if bitrate is not None:
                PACKET_INTERVAL_MAP[full_path] = calculate_packet_interval(bitrate)
                logging.info(f"Preparado '{full_path}' com intervalo de pacote {PACKET_INTERVAL_MAP[full_path]} segundos.")

def get_video_bitrate(filename):
    cmd = ["ffmpeg", "-i", filename]
    result = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, _ = result.communicate()

    # Procura pelo bitrate na saída do FFmpeg
    matches = re.search(r"bitrate: (\d+) kb/s", stdout.decode('utf-8'))
    if matches:
        return int(matches.group(1)) * 1000  # Converte kbps para bps

    return None  # Retorna None se o bitrate não puder ser extraído

def stream_all_videos(video_folder):
    video_files = list_video_files(video_folder)  # Obtém a lista de arquivos de vídeo
    logging.info(f"Arquivos de vídeo encontrados: {video_files}")

    while True:  # Loop infinito
        for video_file in video_files:
            logging.info(f"Iniciando transmissão do vídeo: {video_file}")
            stream_video(video_file)  # Transmite cada vídeo

def stream_video(video_file):
    global PACKETS_SENT
    with open(video_file, 'rb') as f:
        counter = 0  # Inicializa o contador de pacotes
        packet_transmission_time = PACKET_INTERVAL_MAP[video_file]

        start_time = time.time()

        try:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    # Envia um pacote especial de "fim de transmissão"
                    end_packet = struct.pack('>I', counter) + b'END_OF_STREAM'
                    sock.sendto(end_packet, (MULTICAST_IP, MULTICAST_PORT))
                    PACKETS_SENT += 1
                    logging.info("Fim de transmissão detectado.")
                    break  # Fim do arquivo

                # Precede o contador de 4 bytes
                packet = struct.pack('>I', counter) + chunk

                try:
                    # Envia o pacote para o grupo multicast
                    sock.sendto(packet, (MULTICAST_IP, MULTICAST_PORT))
                    PACKETS_SENT += 1
                except socket.error as e:
                    logging.error(f"Falha ao enviar dados para o grupo multicast {MULTICAST_IP}:{MULTICAST_PORT}: {e}")
                    continue  # Pula para a próxima iteração do loop

                counter = (counter + 1) % (2 ** 32)

                # Calcula o tempo para enviar o próximo pacote
                next_packet_time = start_time + (counter * packet_transmission_time)
                time_to_wait = next_packet_time - time.time()
                if time_to_wait > 0:
                    time.sleep(time_to_wait)
        except KeyboardInterrupt:
            logging.info("Servidor encerrando por KeyboardInterrupt.")
            logging.info(f"Pacotes enviados: {PACKETS_SENT}")
            sys.exit(0)

# Preparar a lista de arquivos de vídeo e seus intervalos de pacotes
prepare_video_files(VIDEO_FOLDER)

# Chama stream_all_videos com o caminho para a pasta de vídeos
stream_all_videos(VIDEO_FOLDER)