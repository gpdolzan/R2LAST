#!/bin/bash

INPUT_FILE="chika.mp4"
TOTAL_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$INPUT_FILE")
NUM_SEGMENTS=15
SEGMENT_DURATION=$(echo "$TOTAL_DURATION / $NUM_SEGMENTS" | bc -l)

ffmpeg -i "$INPUT_FILE" -c copy -map 0 -f segment -segment_time "$SEGMENT_DURATION" -segment_format video/mpegts chika%03d.ts