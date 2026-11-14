FROM python:3.11-slim

ARG RELEASE_SHA
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
LABEL org.opencontainers.image.revision=$RELEASE_SHA

WORKDIR /app

ARG DEBIAN_MIRROR=deb.debian.org
RUN sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --index-url "$PIP_INDEX_URL" -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
