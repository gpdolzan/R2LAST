import socket
import subprocess
import sys
import threading

# Client configuration
SERVER_IP = sys.argv[1]
SERVER_PORT = 8521  # Communicate with the server via this port

BUFFER_SIZE = 1472
PORT_INITIAL_RANGE = 8523
PORT_FINAL_RANGE = 8623
player = None

sock = None  # Declare the socket globally

def cleanup_and_exit():
    # Function to deregister from the server and print info before exiting
    global out_of_order_counter, lost_packets_counter, sock, player
    player.terminate()
    try:
        if sock:
            # Send the deregisteruser message to the server
            sock.sendto(b'deregisteruser', (SERVER_IP, SERVER_PORT))
            # Wait for the deregisteruserok confirmation from the server
            while True:
                try:
                    data, _ = sock.recvfrom(BUFFER_SIZE)
                    if data == b'deregisteruserok':
                        print("Deregistered successfully.")
                        break
                except socket.timeout:
                    print("No response from server on deregister. Exiting anyway.")
                    break
    finally:
        print_info_and_exit()

def print_info_and_exit():
    global out_of_order_counter, lost_packets_counter, player
    # Calculate lost packets (gaps in the sequence)
    if sock:
        sock.close()
    lost_packets_counter += sum(1 for i in range(last_counter + 1, max(buffer.keys(), default=0) + 1) if i not in buffer)
    player.terminate()
    print(f"Packets that arrived out of order: {out_of_order_counter}")
    print(f"Packets that never arrived: {lost_packets_counter}")
    sys.exit(0)

def main():
    global out_of_order_counter, lost_packets_counter, buffer, last_counter, sock, player
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Try to bind to an available port
    for port in range(PORT_INITIAL_RANGE, PORT_FINAL_RANGE + 1):
        try:
            sock.bind(('', port))
            print(f"Socket successfully bound to port {sock.getsockname()[1]}")
            break
        except socket.error:
            continue
    else:
        print("It was not possible to bind to any port in the range 8523-8623.")
        sys.exit()

    # Register with the server
    sock.sendto(b'registerclient', (SERVER_IP, SERVER_PORT))

    while True:
        # Wait for 'registerclientok' from the server
        data, addr = sock.recvfrom(BUFFER_SIZE)
        if data == b'registerclientok':
            print("Successfully registered!")
            break

    # wait for streamstart message
    while True:
        # remove counter from the message
        data, addr = sock.recvfrom(BUFFER_SIZE)
        if data[4:] == b'streamstart':
            print("Server started streaming.")
            break

    # Start a VLC instance as a subprocess
    player = subprocess.Popen(["vlc", "fd://0"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    last_counter = 1
    buffer = {}  # Buffer for out-of-order packets
    out_of_order_counter = 0
    lost_packets_counter = 0

    # Set a timeout for the socket
    sock.settimeout(2)  # Set the timeout to 2 seconds

    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            counter = int.from_bytes(data[:4], 'big')

            # check for streamshutdown message
            if data[4:] == b'streamshutdown':
                print("Server finished streaming. Exiting gracefully...")
                print_info_and_exit()

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
                if counter > last_counter + 1:
                    out_of_order_counter += 1
        except socket.timeout:
            player.stdin.flush()
            last_counter = 1  # Reset counter if needed
            buffer.clear()    # Clear the buffer to avoid playing old frames
            continue  # Continue with the next iteration of the loop

if __name__ == '__main__':
    main()
