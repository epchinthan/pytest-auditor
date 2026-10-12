FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY __main__.py __init__.py web_server.py web_sources.py ./
COPY core/ ./core/
COPY scanning/ ./scanning/
COPY reporting/ ./reporting/
COPY web/ ./web/

EXPOSE 6767
STOPSIGNAL SIGINT
CMD ["python", "/app/web_server.py", "--host", "0.0.0.0", "--port", "6767"]
