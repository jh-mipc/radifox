ARG DCM2NIIX_VERSION=1.0.20230411
ARG PYTHON_VERSION=3.11.6
ARG DEBIAN_VERSION=bullseye

FROM python:${PYTHON_VERSION}-slim-${DEBIAN_VERSION}
LABEL maintainer=blake.dewey@jhu.edu
ARG DCM2NIIX_VERSION
ARG PYTHON_VERSION
ARG DEBIAN_VERSION

RUN apt-get update && \
    apt-get -y --no-install-recommends install ca-certificates git unzip curl

RUN cd /tmp && \
    curl -L -o dcm2niix_lnx.zip https://github.com/rordenlab/dcm2niix/releases/download/v${DCM2NIIX_VERSION}/dcm2niix_lnx.zip && \
    unzip dcm2niix_lnx.zip && \
    mkdir -p /opt/dcm2niix/bin && \
    mv dcm2niix /opt/dcm2niix/bin && \
    rm -f /tmp/dcm2niix_lnx.zip

# Update environment variables
ENV PATH /opt/dcm2niix/bin:${PATH}

# Create manifest json file
RUN echo -e "{\n \
    \"DCM2NIIX_VERSION\": \"${DCM2NIIX_VERSION}\",\n \
    \"PYTHON_VERSION\": \"${PYTHON_VERSION}\",\n \
    \"DEBIAN_VERSION\": \"${DEBIAN_VERSION}\"\n \
}" > /opt/manifest.json

# Copy package and install
COPY requirements.txt /tmp/autoconv-src/requirements.txt
RUN pip install --no-cache-dir -r /tmp/autoconv-src/requirements.txt
COPY . /tmp/autoconv-src/
RUN pip install --no-cache-dir /tmp/autoconv-src/ && \
    rm -rf /tmp/autoconv-src/

ENTRYPOINT 'autoconv-convert'
