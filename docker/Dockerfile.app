# The image every participant app runs in, on laptops and on the Raspberry Pi (multi-arch).
# The app's code is mounted at /app; the SDK is mounted from the repo so fixes need no rebuild.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_ROOT_USER_ACTION=ignore PYTHONPATH=/sdk PYTHONUSERBASE=/deps
RUN pip install --no-cache-dir "pyzmq>=26" "numpy>=1.26" "opencv-python-headless>=4.9" "pyyaml>=6"
COPY packages/sdk /sdk
COPY docker/app-entrypoint.sh /usr/local/bin/app-entrypoint
RUN chmod +x /usr/local/bin/app-entrypoint

WORKDIR /app
ENTRYPOINT ["app-entrypoint"]
