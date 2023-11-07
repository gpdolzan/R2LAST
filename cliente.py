import socket
import struct
import subprocess

# Client configuration
MULTICAST_IP = '224.0.0.1'
MULTICAST_PORT = 5004
CHUNK_SIZE = 1472  # Packet size including 4 bytes for the counter
CLIENT_INTERFACE_IP = '0.0.0.0'  # Use the appropriate interface IP if needed

# Create a UDP socket
client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Allow multiple clients on the same machine (for testing purposes)
client_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

# Bind to the server address
client_sock.bind((CLIENT_INTERFACE_IP, MULTICAST_PORT))

# Tell the operating system to add the socket to the multicast group
group = socket.inet_aton(MULTICAST_IP) + socket.inet_aton(CLIENT_INTERFACE_IP)
client_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, group)

# Initialize counters
expected_packet_counter = None
lost_packets = 0
out_of_order_packets = 0

# Prepare VLC subprocess command
vlc_command = "vlc -"  # The dash '-' tells VLC to accept input from stdin

# Start VLC as a subprocess
vlc_process = subprocess.Popen(["vlc", "fd://0"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    while True:
        # Receive packet
        data, address = client_sock.recvfrom(CHUNK_SIZE)

        # Check for "end-of-stream" packet
        if data[4:] == b'END_OF_STREAM':
            print("End of stream detected, resetting counter.")
            expected_packet_counter = None
            continue

        # Extract packet counter
        packet_counter, = struct.unpack('>I', data[:4])
        video_data = data[4:]

        if expected_packet_counter is None:
            # This is the first packet received; set the initial expected counter
            expected_packet_counter = packet_counter
        else:
            if packet_counter != expected_packet_counter:
                # Packet is out of order or missing
                if packet_counter < expected_packet_counter:
                    # Packet is out of order
                    out_of_order_packets += 1
                else:
                    # Some packets were missed
                    lost_packets += packet_counter - expected_packet_counter

                # Log the packet issue
                print(f"Packet issue detected. Expected: {expected_packet_counter}, Received: {packet_counter}")

            # Set the next expected packet counter
            expected_packet_counter = (packet_counter + 1) % (2 ** 32)

        # Write the video data to VLC's stdin
        vlc_process.stdin.write(video_data)

except KeyboardInterrupt:
    print("Exiting client...")

finally:
    # Close VLC process
    if vlc_process:
        vlc_process.terminate()

    # Close the socket
    client_sock.close()

    # Log final statistics
    print(f"Total lost packets: {lost_packets}. Total out of order packets: {out_of_order_packets}.")
