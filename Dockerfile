FROM python:3.11-slim
WORKDIR /moogly

COPY requirements.txt .
COPY moogly.py .
COPY dyes_fr.json .

RUN pip install -r requirements.txt

ENTRYPOINT ["python3", "moogly.py"]