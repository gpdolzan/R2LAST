import socket
import subprocess
import sys

# Configuração do cliente
SERVER_IP = sys.argv[1]
SERVER_PORT = 8521 # Communicate with the server via this port

BUFFER_SIZE = 1472
PORT_INITIAL_RANGE = 8523
PORT_FINAL_RANGE = 8623

def start_vlc_instance():
    return subprocess.Popen(
        ["vlc", "-"], 
        stdin=subprocess.PIPE
    )

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # try to bind to an available port
    for port in range(PORT_INITIAL_RANGE, PORT_FINAL_RANGE + 1):
        try:
            sock.bind(('', port))
            print(f"Socket ligado com sucesso à porta {sock.getsockname()[1]}")
            break
        except socket.error:
            continue
    else:
        print("Não foi possível ligar a nenhuma porta no intervalo 8523-8623.")
        sys.exit()

    # Registrar com o servidor
    sock.sendto(b'registerclient', (SERVER_IP, SERVER_PORT))

    # Esperar 'registerclientok' do servidor
    data, addr = sock.recvfrom(BUFFER_SIZE)
    if data != b'registerclientok':
        print("Erro ao registrar com o servidor.")
        sys.exit()
    else:
        print("Registrado com sucesso!")

    # Inicie uma instância do VLC como subprocesso
    player = start_vlc_instance()

    last_counter = 1
    buffer = {}  # Buffer para pacotes fora de ordem

    # Set the socket timeout to 3 seconds
    sock.settimeout(3)

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            counter = int.from_bytes(data[:4], 'big')

            if counter == last_counter + 1:
                player.stdin.write(data[4:])
                player.stdin.flush()  # Ensure data is sent to VLC immediately
                last_counter += 1

                # Check for subsequent packets in the buffer
                while last_counter + 1 in buffer:
                    player.stdin.write(buffer[last_counter + 1])
                    del buffer[last_counter + 1]
                    last_counter += 1
            else:
                # Store the packet in the buffer if it arrives out of order
                buffer[counter] = data[4:]

        except socket.timeout:
            # Handle timeout, e.g., by resetting the counter and flushing the buffer
            print("Timeout occurred, resetting VLC...")
            last_counter = 0
            buffer.clear()

if __name__ == '__main__':
    main()