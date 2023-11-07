import socket
import time
import threading
import subprocess
import re
import os
from moviepy.editor import VideoFileClip

# Server configuration
VIDEO_FOLDER = "video"
SERVER_PORT = 8521
BUFFER_SIZE = 1472  # MTU IPV4 - 20 (IP header) - 8 (UDP header)

clients = set()  # Set of registered clients
clients_lock = threading.Lock()  # Lock for accessing the clients set

# Function to list all video files in a directory
def list_video_files(directory):
    return [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]

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
                with clients_lock:  # Acquire lock before accessing the clients set
                    clients.add(addr)
                s.sendto(b'registerclientok', addr)
                print(f"Client registered: {addr}")
            elif data == b'deregisteruser':  # Handle deregistration
                with clients_lock:  # Acquire lock before accessing the clients set
                    if addr in clients:
                        clients.remove(addr)
                        s.sendto(b'deregisteruserok', addr)  # Send confirmation back to the client
                        print(f"Client deregistered: {addr}")
                    else:
                        print(f"Client not found in registration list: {addr}")
            else:
                print(f"Invalid command received from {addr}: {data}")
        except socket.timeout:
            continue  # If a timeout occurs, just continue and check the event again
        except OSError:
            if stop_event.is_set():
                # If the stop event is set, it means we're shutting down, so break out of the loop
                break
            else:
                # Re-raise the exception if it's not part of the shutdown process
                raise

def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("", SERVER_PORT))
    s.settimeout(1)

    print(f"Server started on port {SERVER_PORT}!")

    stop_event = threading.Event()    
    client_listener_thread = threading.Thread(target=listen_for_clients, args=(s, stop_event), daemon=True)
    client_listener_thread.start()

    video_files = list_video_files(VIDEO_FOLDER)  # List video files in the folder

    input("Enter quando estiverem conectados")

    try:
        while not stop_event.is_set():  # Loop continuously until stopped

            # while client set is empty, wait
            while not clients:
                pass

            for video_file in video_files:  # Iterate over each video file
                print(f"Starting video stream for {video_file}...")

                BITRATE = get_video_bitrate(video_file) or 5000000
                BYTES_PER_SECOND = BITRATE / 8
                VIDEO_DURATION = get_video_duration(video_file)
                packet_transmission_time = (BUFFER_SIZE - 4) / BYTES_PER_SECOND

                start_time = time.time()

                with clients_lock:  # Acquire lock before iterating over the clients set
                    for client in clients:
                        counter = 1
                        for data in read_video(video_file):
                            packet = counter.to_bytes(4, 'big') + data
                            try:
                                s.sendto(packet, client)
                            except socket.error as e:
                                print(f"Failed to send data to {client}: {e}")
                                continue

                            counter = (counter + 1) % (2 ** 32)

                            next_packet_time = start_time + (counter * packet_transmission_time)
                            while time.time() < next_packet_time:
                                if stop_event.is_set():
                                    break  # Exit if stop event is set
                                time.sleep(0.001)  # Sleep briefly to avoid a busy wait

                time.sleep(3)  # Wait for the duration of the video before starting the next
                if stop_event.is_set():
                    break  # Exit if stop event is set

    except KeyboardInterrupt:
        print("Shutdown signal received. Ending the stream...")
        stop_event.set()

    finally:
        # Clean up the resources
        with clients_lock:  # Acquire lock before notifying clients of shutdown
            for client in clients:
                s.sendto(b"streamshutdown", client)
        s.close()
        client_listener_thread.join()
        print("Server shut down gracefully.")

if __name__ == '__main__':
    main()
