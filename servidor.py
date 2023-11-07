import socket
import struct
import logging
import subprocess
import re
import os
import time
from moviepy.editor import VideoFileClip

# Server configuration
VIDEO_FOLDER = "video"
MULTICAST_IP = '224.0.0.1'
MULTICAST_PORT = 5004
CHUNK_SIZE = 1468 # Packet size minus 4 bytes for the counter

# Create the datagram socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Set the time-to-live for messages to 1 so they do not go past the local network segment.
ttl = struct.pack('b', 1)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

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

def stream_all_videos(video_folder):
    video_files = list_video_files(video_folder)  # Get the list of video files

    while True:  # Loop forever
        for video_file in video_files:
            print(f"Streaming video: {video_file}")
            stream_video(video_file)  # Stream each video
            time.sleep(3)  # Wait a bit before streaming the next video (optional)

def stream_video(video_file):
    with open(video_file, 'rb') as f:
        counter = 0  # Initialize packet counter
        bitrate = get_video_bitrate(video_file)  # in bits per second

        if bitrate is None:
            raise ValueError("Could not determine video bitrate")

        # Calculate the time interval between packets in seconds
        packet_transmission_time = (CHUNK_SIZE * 8) / bitrate  # convert CHUNK_SIZE to bits

        start_time = time.time()

        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                # Send a special "end-of-stream" packet
                end_packet = struct.pack('>I', counter) + b'END_OF_STREAM'
                sock.sendto(end_packet, (MULTICAST_IP, MULTICAST_PORT))
                break  # End of file

            # Prepend the 4-byte counter
            packet = struct.pack('>I', counter) + chunk

            try:
                # Send the packet to the multicast group
                sock.sendto(packet, (MULTICAST_IP, MULTICAST_PORT))
            except socket.error as e:
                print(f"Failed to send data to multicast group {MULTICAST_IP}:{MULTICAST_PORT}: {e}")
                continue  # Skip to the next loop iteration

            counter = (counter + 1) % (2 ** 32)

            # Calculate the time to send the next packet
            next_packet_time = start_time + (counter * packet_transmission_time)
            time_to_wait = next_packet_time - time.time()
            if time_to_wait > 0:
                time.sleep(time_to_wait)

        # Wait a short time before streaming the next video
        time.sleep(3)

# Call stream_all_videos with the path to your video folder
stream_all_videos(VIDEO_FOLDER)