FROM ubuntu:noble AS val3dity_builder

ARG VAL3DITY_SRC="https://github.com/tudelft3d/val3dity/archive/refs/tags/2.4.0.tar.gz"

WORKDIR /src

RUN apt update \
    && apt-get install -y build-essential libboost-filesystem1.83-dev libeigen3-dev libgeos++-dev  \
      libcgal-dev wget cmake

RUN wget "${VAL3DITY_SRC}" -O val3dity-src.tar.gz \
    && mkdir val3dity \
    && cd val3dity \
    && tar xf ../val3dity-src.tar.gz --strip-components=1 \
    && mkdir build \
    && cd build \
    && cmake .. \
    && make

FROM eclipse-temurin:17-noble AS runner

ARG CITYGML_TOOLS="https://github.com/citygml4j/citygml-tools/releases/download/v2.3.0/citygml-tools-2.3.0.zip"

COPY --from=val3dity_builder /src/val3dity/build/val3dity /usr/bin/val3dity

WORKDIR /opt

RUN apt update \
    && apt-get install -y libboost-filesystem1.83 libgeos-c1t64 wget unzip python3-pip git

RUN wget "${CITYGML_TOOLS}" -O /tmp/citygml-tools.zip \
    && unzip /tmp/citygml-tools.zip \
    && ln -s citygml-tools-* citygml-tools

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --upgrade -r requirements.txt --break-system-packages

COPY data ./data
COPY app ./app

ENV CITYGML_TOOLS="/opt/citygml-tools/citygml-tools"
ENV VAL3DITY="/usr/bin/val3dity"
ENV ROOT_PATH=""

CMD ["bash", "-c", "fastapi run app/main.py --proxy-headers --port 8080 --root-path ${ROOT_PATH%/}"]
