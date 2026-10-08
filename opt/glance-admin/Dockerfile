FROM python:3.12-alpine
ENV PYTHONUNBUFFERED=1
RUN adduser -D -u 1000 app
WORKDIR /app
COPY app.py infra.py net.py tools.py releases.py cameras.py channels.py bookmarks.py news.py dev.py shop.py vpn.py remote.py work.py ./
USER app
EXPOSE 3005
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:3005/health >/dev/null || exit 1
CMD ["python", "app.py"]
