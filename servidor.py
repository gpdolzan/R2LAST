import socket
import time
import threading
import subprocess
import re
from moviepy.editor import VideoFileClip

# Configuração do servidor
VIDEO = "video/chika.ts"
SERVER_PORT = 8521
BUFFER_SIZE = 1472  # MTU IPV4 - 20 (IP header) - 8 (UDP header)

clients = set()  # Lista de clientes registrados

def get_video_bitrate(filename):
    cmd = ["ffmpeg", "-i", filename]
    result = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout, _ = result.communicate()

    # Search for bitrate in the FFmpeg output
    matches = re.search(r"bitrate: (\d+) kb/s", stdout.decode('utf-8'))
    if matches:
        return int(matches.group(1)) * 1000  # Convert kbps to bps

    return None  # Return None if bitrate couldn't be extracted

def get_video_duration(filename):
    clip = VideoFileClip(filename)
    duration = clip.duration
    clip.close()
    return duration

def read_video(filename):
    with open(filename, 'rb') as file:
        while True:
            data = file.read(BUFFER_SIZE - 4)  # 4 bytes reserved for the counter
            if not data:
                break
            yield data

def listen_for_clients(s, stop_event):
    while not stop_event.is_set():
        try:
            data, addr = s.recvfrom(BUFFER_SIZE)
            if data == b'registerclient':
                # send 'registerclientok' to the client
                s.sendto(b'registerclientok', addr)
                clients.add(addr)
                print(f"Cliente registrado: {addr}")
            else:
                print(f"Comando inválido recebido de {addr}: {data}")
        except socket.timeout:
            continue  # If a timeout occurs, just continue and check the event again

BITRATE = get_video_bitrate(VIDEO) or 5000000
BYTES_PER_SECOND = BITRATE / 8
VIDEO_DURATION = get_video_duration(VIDEO)

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", SERVER_PORT))
    s.settimeout(1)

    print(f"Servidor iniciado!")

    stop_event = threading.Event()  # Create an event object    
    # Start listening for clients in a separate thread
    client_listener_thread = threading.Thread(target=listen_for_clients, args=(s,stop_event), daemon=True)
    client_listener_thread.start()

    input("Press enter to start the video stream...")

    # Join the listening thread if needed
    stop_event.set()
    client_listener_thread.join()

    # Imprimir que estamos começando a transmitir
    print("Iniciando transmissão de vídeo...")

    # Packet transmission time in seconds
    packet_transmission_time = (BUFFER_SIZE - 4) / BYTES_PER_SECOND

    # Loop until user interrupts
    while True:
        start_time = time.time()

        # Send the video to all registered clients
        for client in clients:
            counter = 1  # Initialize packet counter
            for data in read_video(VIDEO):
                # Prepend the counter to the data
                packet = counter.to_bytes(4, 'big') + data

                # Non-blocking send
                try:
                    s.sendto(packet, client)
                except socket.error as e:
                    print(f"Failed to send data to {client}: {e}")
                    continue  # Skip this packet

                # update counter and check for overflow
                counter = (counter + 1) % (2 ** 32)

                # Wait until it's time for the next packet
                next_packet_time = start_time + (counter * packet_transmission_time)
                while time.time() < next_packet_time:
                    pass  # Busy wait

        time.sleep(5) # Wait 5 seconds before restarting the transmission
        print("Reiniciando transmissão...")

if __name__ == '__main__':
    main()