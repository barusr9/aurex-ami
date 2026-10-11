# Ami as a long-lived service with a disk: the straightforward deployment.
#   docker build -t ami .
#   docker run -p 8000:8000 --env-file .env -v ami-state:/app/state -v ami-cache:/app/.cache ami
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000 HOST=0.0.0.0 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "web.py"]
