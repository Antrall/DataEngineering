FROM python:3.12-slim

WORKDIR /app

COPY docker/requirements.txt requirements.txt
RUN --mount=type=secret,id=cabundle,required=false \
    if [ -f /run/secrets/cabundle ]; then export PIP_CERT=/run/secrets/cabundle; fi; \
    pip install --no-cache-dir -r requirements.txt

COPY src /app/DataEngineering/HW5/src
ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "DataEngineering.HW5.src.pairs_job"]
