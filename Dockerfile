ARG PYTHON_VERSION=3.11.6
ARG DEBIAN_VERSION=bookworm

FROM python:${PYTHON_VERSION}-slim-${DEBIAN_VERSION}
LABEL maintainer=blake.dewey@jhu.edu
ARG PYTHON_VERSION
ARG DEBIAN_VERSION

ENV PYTHONUSERBASE=/opt/python

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# Create manifest json file
RUN echo -e "{\n \
    \"PYTHON_VERSION\": \"${PYTHON_VERSION}\",\n \
    \"DEBIAN_VERSION\": \"${DEBIAN_VERSION}\"\n \
}" > /opt/manifest.json

# Copy package and install
COPY . /tmp/radifox-src/
RUN pip install --no-cache-dir /tmp/radifox-src/ && \
    rm -rf /tmp/radifox-src/

ENTRYPOINT ["/bin/bash"]
