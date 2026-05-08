FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY main.py ./

RUN pip install --no-cache-dir .

EXPOSE 9108

ENTRYPOINT ["pylinode-vlan-topology-exporter"]
