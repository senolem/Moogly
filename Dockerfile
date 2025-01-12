FROM python
WORKDIR /moogly

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY moogly.py .
COPY dyes_fr.json .

ENTRYPOINT ["tail", "-f", "/dev/null"]