FROM registry.gitlab.com/neurobuilds/miniconda:3.9.7-ubuntu20.04 as conda

FROM ubuntu:20.04
COPY --from=conda /opt/conda /opt/conda
ENV PATH /opt/conda/bin:${PATH}

RUN conda install -y flask gunicorn && \
    conda clean -ya

RUN mkdir -p /opt/qa_flask
COPY app.py /opt/qa_flask
COPY templates /opt/qa_flask/templates

WORKDIR /opt/qa_flask
EXPOSE 5000
ENTRYPOINT gunicorn --chdir /opt/qa_flask -b 0.0.0.0:5000 app:app