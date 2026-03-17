FROM python:3.12-alpine

# Install everything and keep it all
RUN apk add --no-cache \
        git \
        libffi-dev \
        musl-dev \
        gcc \
        g++ \
        leveldb-dev \
        make \
        zlib-dev \
        tiff-dev \
        freetype-dev \
        libpng-dev \
        libjpeg-turbo-dev \
        lcms2-dev \
        libwebp-dev \
        openssl-dev \
        cargo \
        fastfetch \
        libstdc++ \
        snappy

# Set up venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install bot
RUN mkdir -p /src
WORKDIR /src
COPY . .
RUN pip install wheel && pip install .[fast] && pip install uvloop

# Create bot user and data dir
RUN adduser -D pyrobud && mkdir -p /data && chown pyrobud:pyrobud /data
VOLUME ["/data"]

USER pyrobud
WORKDIR /data
CMD ["pyrobud"]
