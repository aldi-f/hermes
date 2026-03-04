FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

RUN groupadd -r hermes && useradd -r -g hermes hermes

COPY src/ src/
COPY config/ config/

RUN chown -R hermes:hermes /app

EXPOSE 8080 9090

USER hermes

CMD ["python", "-m", "src.main"]
