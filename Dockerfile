FROM python:3.7-buster

# RUN apk add build-base
RUN apt-get -y update
RUN apt-get install -y sqlite3 libsqlite3-dev

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./run.py" ]