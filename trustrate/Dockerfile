FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY service service
COPY pipeline pipeline
EXPOSE 8000
CMD ["uvicorn","service.app.main:app","--host","0.0.0.0","--port","8000"]
