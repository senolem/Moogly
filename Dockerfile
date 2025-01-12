FROM python:3.11-slim

WORKDIR /moogly
RUN apt-get update && apt-get install git -y
RUN git clone https://github.com/senolem/Moogly ./

RUN pip install --root-user-action=ignore -r requirements.txt

CMD ["python3", "moogly.py"]