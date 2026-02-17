FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY src/ src/
COPY config/ config/

EXPOSE 8080 9090

CMD ["python", "-m", "src.main"]
