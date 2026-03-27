FROM golang:1.23-bookworm AS corrupter
WORKDIR /build
RUN git clone --depth 1 https://github.com/r00tman/corrupter . \
    && CGO_ENABLED=0 go build -ldflags="-s -w" -o /corrupter .

FROM python:3.12-slim

COPY --from=corrupter /corrupter /usr/local/bin/corrupter

# Install build and runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        gcc \
        g++ \
        make \
        libleveldb-dev \
        libffi-dev \
        libsnappy-dev \
        zlib1g-dev \
        libtiff-dev \
        libfreetype-dev \
        libpng-dev \
        libjpeg-dev \
        liblcms2-dev \
        libwebp-dev \
        libssl-dev \
        cargo \
        fastfetch \
    && rm -rf /var/lib/apt/lists/*

# Set up venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install bot
RUN mkdir -p /src
WORKDIR /src
COPY . .
RUN pip install wheel && pip install .[fast] && pip install uvloop

# Create bot user and data dir
RUN adduser --disabled-password --gecos "" pyrobud && mkdir -p /data && chown pyrobud:pyrobud /data
VOLUME ["/data"]

USER pyrobud
WORKDIR /data
CMD ["pyrobud"]
