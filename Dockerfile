FROM python:3.11-slim

WORKDIR /moogly
RUN apt-get update && apt-get install git -y
COPY entry.sh ./entry.sh

CMD ["/bin/bash", "entry.sh"]