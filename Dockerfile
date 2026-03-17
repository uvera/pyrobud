FROM python:3.12-slim

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
