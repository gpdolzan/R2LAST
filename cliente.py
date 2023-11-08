import socket
import struct
import subprocess
import logging
from datetime import datetime

# Configuração do cliente
MULTICAST_IP = '224.0.0.1'
MULTICAST_PORT = 5004
CHUNK_SIZE = 1472  # Tamanho do pacote incluindo 4 bytes para o contador
CLIENT_INTERFACE_IP = '0.0.0.0'  # Use o IP de interface apropriado se necessário
PACKETS_RECEIVED = 0

# Configuração do logging
log_filename = datetime.now().strftime("cliente_%H%M%S.txt")
logging.basicConfig(filename=log_filename,
                    filemode='w',
                    level=logging.DEBUG,
                    format='CLIENTE - %(asctime)s - %(levelname)s - %(message)s')

# Criar um socket UDP
client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
logging.info("Socket criado.")

# Permitir múltiplos clientes na mesma máquina (para fins de teste)
client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
logging.info("Socket configurado para permitir múltiplos clientes.")

# Vincular ao endereço do servidor
client_sock.bind((CLIENT_INTERFACE_IP, MULTICAST_PORT))
logging.info(f"Socket vinculado a {CLIENT_INTERFACE_IP}:{MULTICAST_PORT}.")

# Dizer ao sistema operacional para adicionar o socket ao grupo multicast
group = socket.inet_aton(MULTICAST_IP) + socket.inet_aton(CLIENT_INTERFACE_IP)
client_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group)
logging.info(f"Socket adicionado ao grupo multicast {MULTICAST_IP}.")

# Inicializar contadores
expected_packet_counter = None
lost_packets = 0
out_of_order_packets = 0

# Preparar comando subprocess para VLC
vlc_command = "vlc -"  # O traço '-' diz ao VLC para aceitar entrada do stdin

# Iniciar VLC como um subprocesso
vlc_process = subprocess.Popen(["vlc", "fd://0"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
logging.info("Processo VLC iniciado.")
logging.info("Iniciando loop de recebimento de pacotes.")

try:
    while True:
        # Receber pacote
        data, address = client_sock.recvfrom(CHUNK_SIZE)

        # Verificar pacote "fim-de-stream"
        if data[4:] == b'END_OF_STREAM':
            PACKETS_RECEIVED += 1
            logging.info("Fim do stream detectado, redefinindo contador.")
            expected_packet_counter = None
            continue

        # Extrair contador de pacotes
        packet_counter, = struct.unpack('>I', data[:4])
        video_data = data[4:]

        # Se for o primeiro pacote ou se for o pacote esperado
        if expected_packet_counter is None or packet_counter == expected_packet_counter:
            PACKETS_RECEIVED += 1
            # Atualiza o contador esperado para o próximo pacote
            if expected_packet_counter is None:
                logging.info(f"Primeiro pacote recebido com contador {packet_counter}")
            expected_packet_counter = (packet_counter + 1) % (2 ** 32)
        else:
            if packet_counter < expected_packet_counter:
                PACKETS_RECEIVED += 1
                # Pacote fora de ordem
                out_of_order_packets += 1
                logging.warning(f"Pacote fora de ordem. Esperado: {expected_packet_counter}, Recebido: {packet_counter}")
            else:
                # Pacotes perdidos
                lost_packets += packet_counter - expected_packet_counter
                expected_packet_counter = (packet_counter + 1) % (2 ** 32)
                if lost_packets > 0:  # Registra apenas se houver pacotes perdidos
                    logging.warning(f"Pacotes perdidos. Esperado: {expected_packet_counter-1}, Recebido: {packet_counter}")

            # Definir o próximo contador de pacote esperado
            expected_packet_counter = (packet_counter + 1) % (2 ** 32)

        # Escrever os dados do vídeo no stdin do VLC
        vlc_process.stdin.write(video_data)

except KeyboardInterrupt:
    logging.info("Cliente encerrando por KeyboardInterrupt.")
    logging.info(f"Pacotes recebidos: {PACKETS_RECEIVED}")

finally:
    # Fechar processo VLC
    if vlc_process:
        vlc_process.terminate()
        logging.info("Processo VLC terminado.")

    # Fechar o socket
    client_sock.close()
    logging.info("Socket fechado.")

    # Logar estatísticas finais
    logging.info(f"Total de pacotes perdidos: {lost_packets}. Total de pacotes fora de ordem: {out_of_order_packets}.")
