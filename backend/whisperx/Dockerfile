FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir "whisperlivekit[cpu]"

EXPOSE 8000

ENTRYPOINT ["wlk"]
CMD ["--host", "0.0.0.0", "--port", "8000", \
     "--model", "small", \
     "--language", "ko"]
