FROM python
WORKDIR /moogly

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY moogly.py .
COPY dyes_fr.json .

ENTRYPOINT ["sh", "-c", "python3 /moogly/moogly.py && tail -f /dev/null"]