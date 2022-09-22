FROM python:3.8.2-slim-buster as build_stage
LABEL maintainer=blake.dewey@jhu.edu

# Install variables
ARG N_CPU=1
ENV DCM2NIIX_VERSION 1.0.20200331
ENV DCM2NIIX_COMMIT_HASH 93e4f454cfe2fad5fca21ab4d2eb2862755bd21c
ENV DCM2NIIX_GIT https://github.com/rordenlab/dcm2niix.git
ENV DCM4CHE_VERSION 5.22.1
ENV DCMTK_VERSION 3.6.5
ENV PYTHON_BASE_VERSION 3
ENV PYTHON_VERSION 3.8.2

# Software directories
ENV SOFTDIR /opt/software
ENV BUILDDIR /opt/build
RUN mkdir -p ${SOFTDIR} ${BUILDDIR}

# Update and install system software
RUN mkdir /usr/share/man/man1/
RUN \
    apt-get update && \
    apt-get -y install \
        wget \
        bzip2 \
        curl \
        g++ \
        cmake \
        git \
        default-jre-headless \
        cmake \
        unzip

# Install dcm2niix
RUN \
	cd ${BUILDDIR} && \
	git clone ${DCM2NIIX_GIT} dcm2niix && \
    cd dcm2niix && \
    if [ ${DCM2NIIX_VERSION} == 'dev' ]; then git checkout $DCM2NIIX_COMMIT_HASH; else git checkout tags/v$DCM2NIIX_VERSION; fi && \
    cd ${BUILDDIR} && \
    mkdir dcm2niix-build && \
    cd dcm2niix-build && \
    cmake ../dcm2niix -DCMAKE_INSTALL_PREFIX=${SOFTDIR}/dcm2niix \
        -DUSE_GIT_PROTOCOL=OFF \
        -DCMAKE_BUILD_TYPE=Release \
        -DZLIB_IMPLEMENTATION=Cloudflare \
        -DUSE_JPEGLS=ON \
        -DUSE_OPENJPEG=ON \
        -DBATCH_VERSION=ON && \
    make -j ${N_CPU} && \
    make install

# Install dcm4che
RUN \
    cd ${BUILDDIR} && \
    curl -L -o dcm4che-${DCM4CHE_VERSION}-bin.zip https://sourceforge.net/projects/dcm4che/files/dcm4che3/${DCM4CHE_VERSION}/dcm4che-${DCM4CHE_VERSION}-bin.zip/download && \
    unzip dcm4che-${DCM4CHE_VERSION}-bin.zip && \
    mv dcm4che-${DCM4CHE_VERSION} ${SOFTDIR}/dcm4che

# Install dcmtk
RUN \
    cd ${BUILDDIR} && \
    curl -L -o DCMTK-${DCMTK_VERSION}.tar.gz  https://github.com/DCMTK/dcmtk/archive/DCMTK-${DCMTK_VERSION}.tar.gz && \
    tar -xzf DCMTK-${DCMTK_VERSION}.tar.gz && \
    cd dcmtk-DCMTK-${DCMTK_VERSION} && \
    mkdir build && \
    cd build && \
    cmake ../ \
    -DCMAKE_INSTALL_PREFIX=${SOFTDIR}/dcmtk \
    -DDCMTK_ENABLE_BUILTIN_DICTIONARY=ON \
    -DDCMTK_ENABLE_EXTERNAL_DICTIONARY=OFF && \
    make -j ${N_CPU} && \
    make install

# Install python dependencies
WORKDIR ${BUILDDIR}
RUN pip install --upgrade pip wheel
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir ${BUILDDIR}/wheels -r requirements.txt


FROM python:3.8.2-slim-buster
LABEL maintainer=blake.dewey@jhu.edu

# Software directories
ENV SOFTDIR /opt/software
RUN mkdir -p ${SOFTDIR}

# Install java runtime
RUN mkdir /usr/share/man/man1/
RUN apt-get update && \
    apt-get -y install default-jre-headless && \
    apt-get -y --no-install-recommends install git

# Copy python wheels and install
COPY --from=build_stage /opt/build/wheels /wheels
RUN pip install --upgrade pip wheel
RUN pip install --no-cache /wheels/*

# Copy required dcmtk, dcm4che and dcm2niix binaries/libraries
COPY --from=build_stage ${SOFTDIR}/dcmtk/bin/dcmdjpeg ${SOFTDIR}/dcmtk/bin/
COPY --from=build_stage ${SOFTDIR}/dcm4che/bin/emf2sf ${SOFTDIR}/dcm4che/bin/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/dcm4che-tool-emf2sf-5.22.1.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/dcm4che-core-5.22.1.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/dcm4che-emf-5.22.1.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/dcm4che-tool-common-5.22.1.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/slf4j-api-1.7.29.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/slf4j-log4j12-1.7.29.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/log4j-1.2.17.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm4che/lib/commons-cli-1.4.jar ${SOFTDIR}/dcm4che/lib/
COPY --from=build_stage ${SOFTDIR}/dcm2niix/bin/dcm2niix ${SOFTDIR}/dcm2niix/bin/

# Update environment variables
ENV PATH ${SOFTDIR}/dcm2niix/bin:${SOFTDIR}/dcm4che/bin:${SOFTDIR}/dcmtk/bin:${PATH}

# Copy package and install
COPY . /tmp/autoconv-src/
RUN pip install /tmp/autoconv-src/ && \
    rm -rf $/tmp/autoconv-src/

ENTRYPOINT 'autoconv'
