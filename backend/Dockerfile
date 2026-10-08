# One image for both backend programs: the API (the default command) and the
# pipeline (docker compose runs it with `python run_pipeline.py`).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Don't run as root. The files are handed to that user on the way in: a couple
# of them are owner-read-only in the repo and would otherwise be unreadable.
RUN useradd --create-home app
COPY --chown=app:app . .
USER app

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
