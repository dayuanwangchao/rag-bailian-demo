FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data/uploads/.gitkeep ./data/uploads/.gitkeep
COPY data/indexes/.gitkeep ./data/indexes/.gitkeep

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
