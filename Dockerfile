FROM python:3.10-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "metagoofil.py", "-d", "example.com", "-t", "pdf", "-l", "50", "-n", "10", "-o", "results"]
