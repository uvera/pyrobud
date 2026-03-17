# Build Python package and dependencies
FROM python:3.12-alpine AS python-build
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
        cargo
RUN mkdir -p /opt/venv
WORKDIR /opt/venv
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN mkdir -p /src
WORKDIR /src

# Install bot package and dependencies
COPY . .
RUN pip install wheel
RUN pip install .[fast]
RUN pip install uvloop


# Package everything
FROM python:3.12-alpine AS final
# Install optional native tools (for full functionality)
RUN apk add --no-cache fastfetch
# Install native dependencies
RUN apk add --no-cache \
        libffi \
        libstdc++ \
        snappy \
        zlib \
        tiff \
        freetype \
        libpng \
        libjpeg-turbo \
        lcms2 \
        libwebp

# Copy leveldb shared libs from the build stage to ensure ABI match with plyvel
COPY --from=python-build /usr/lib/libleveldb.so* /usr/lib/

# Create bot user
RUN adduser -D pyrobud

# Create data directory for the bot user
RUN mkdir -p /data
RUN chown pyrobud:pyrobud /data

# Ensure we a volume is mounted even if the user doesn't explicitly specify it,
# to prevent unintentional data loss
VOLUME [ "/data" ]

# Copy Python venv
ENV PATH="/opt/venv/bin:$PATH"
COPY --from=python-build /opt/venv /opt/venv

# Set runtime settings
USER pyrobud
WORKDIR /data
CMD ["pyrobud"]
