FROM mcr.microsoft.com/playwright/python:v1.64.0-noble

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies from pyproject.toml; playwright stays pinned to the base image's browsers.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . "playwright==1.64.0"

COPY main.py run_balco_declared.py run_drag_sheets.py run_api.py ./

EXPOSE 8000

CMD ["python", "run_api.py"]
