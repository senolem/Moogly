FROM python
WORKDIR /moogly

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY moogly.py .
COPY dyes_fr.json .
RUN chmod +x moogly.py

ENTRYPOINT python3 /moogly/moogly.py