ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python dependencies
RUN apk add --no-cache \
    py3-pip \
    py3-yaml \
    py3-scipy \
    py3-numpy \
    && pip3 install --no-cache-dir --break-system-packages \
        pyyaml \
        scipy \
        numpy \
        requests \
        "renault-api>=0.5,<1" \
        aiohttp \
    && python3 -c "from scipy.optimize import linprog; print('linprog OK')"

# Copy application files
COPY rootfs /

WORKDIR /app

CMD ["python3", "-u", "/app/main.py"]
