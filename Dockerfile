FROM python:3.12.6-slim

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5005

CMD ["python", "app.py"]