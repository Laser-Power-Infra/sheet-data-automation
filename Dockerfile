FROM mcr.microsoft.com/playwright/python:v1.64.0-noble

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies from pyproject.toml; playwright stays pinned to the base image's browsers.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . "playwright==1.64.0"

COPY main.py run_balco_declared.py run_drag_sheets.py run_api.py ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"

CMD ["python", "run_api.py"]
