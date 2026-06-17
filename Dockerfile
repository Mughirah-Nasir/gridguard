FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY examples ./examples

RUN pip install --no-cache-dir ".[dashboard]"

EXPOSE 8087
# 0.0.0.0 is required *inside* the container so the published port works;
# exposure to the outside world is restricted by the compose file, which
# binds the published port to 127.0.0.1 only. See SECURITY.md.
CMD ["gridguard", "serve", "--schedule", "examples/iesco-f7.json", "--host", "0.0.0.0", "--port", "8087"]
