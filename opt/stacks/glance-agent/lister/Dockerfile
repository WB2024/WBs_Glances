FROM python:3.12-alpine
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY lister.py .
EXPOSE 27974
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:27974/health >/dev/null || exit 1
CMD ["python", "lister.py"]
