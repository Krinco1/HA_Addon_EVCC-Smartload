ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python dependencies
RUN apk add --no-cache python3 py3-pip py3-requests py3-numpy py3-yaml

# Install vehicle API packages (optional – graceful degradation)
RUN pip3 install --no-cache-dir --break-system-packages \
    aiohttp \
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
