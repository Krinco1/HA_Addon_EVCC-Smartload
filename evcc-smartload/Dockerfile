ARG BUILD_FROM
FROM $BUILD_FROM

# Install system packages
RUN apk add --no-cache python3 py3-pip

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    numpy \
    requests \
    aiohttp \
    pyyaml \
    || echo "Core package install issue"

# Install vehicle API packages (optional – graceful degradation)
RUN pip3 install --no-cache-dir --break-system-packages \
    hyundai_kia_connect_api \
    renault-api \
    || echo "Some vehicle API packages could not be installed"

# Copy application code
COPY rootfs/app /app

# Copy config files
COPY config.yaml /app/config.yaml
COPY vehicles.yaml.example /app/vehicles.yaml.example

WORKDIR /app

CMD [ "python3", "/app/main.py" ]
