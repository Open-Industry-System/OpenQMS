FROM pgvector/pgvector:pg15
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential postgresql-server-dev-15 git ca-certificates && \
    git clone https://github.com/xutils/scws.git /tmp/scws && \
    cd /tmp/scws && ./configure && make && make install && ldconfig && \
    git clone https://github.com/amutu/zhparser.git /tmp/zhparser && \
    cd /tmp/zhparser && make USE_PGXS=1 && make USE_PGXS=1 install && \
    apt-get purge -y build-essential git && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /tmp/scws /tmp/zhparser
