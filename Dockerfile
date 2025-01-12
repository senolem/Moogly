FROM python:3.11-slim
WORKDIR /moogly
RUN apt-get update && apt-get install git -y
RUN git clone https://github.com/senolem/Moogly

RUN pip install -r requirements.txt

ENTRYPOINT ["python3", "moogly.py"]