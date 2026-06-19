FROM python:3.12-slim
WORKDIR /app
COPY dashboard/ /app/
EXPOSE 8088
CMD ["python3", "-u", "server.py"]
