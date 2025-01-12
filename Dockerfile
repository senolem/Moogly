FROM python:3.11-slim

RUN apt-get update && apt-get install git -y
RUN git clone https://github.com/senolem/Moogly /moogly

WORKDIR /moogly
RUN pip install -r requirements.txt

ENTRYPOINT ["python3", "moogly.py"]