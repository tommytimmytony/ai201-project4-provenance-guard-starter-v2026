FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/huggingface \
    HOST=0.0.0.0 \
    AI201_DEBUG=0 \
    AI201_LOG_STDOUT=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2,<3.0" \
    && python -m pip install -r requirements.txt

COPY . .

# Put the model in the image so an ephemeral host does not download roughly
# 550 MB every time it wakes up.
RUN python -c "from detector import warm_up; print(warm_up())" \
    && useradd --create-home appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app /opt/huggingface

USER appuser

EXPOSE 8000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]

