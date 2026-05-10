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

# Copy application files (rootfs/ contains /app + /etc/services.d/smartload/)
COPY rootfs /

# Mark service runner executable. Without exec bit s6-overlay silently skips it.
RUN chmod a+x /etc/services.d/smartload/run /etc/services.d/smartload/finish

WORKDIR /app

# No CMD: s6-overlay (from the base-python image) starts and runs
# /etc/services.d/smartload/run, which uses with-contenv → all supervisor env
# vars (SUPERVISOR_TOKEN etc.) reach the python process.
