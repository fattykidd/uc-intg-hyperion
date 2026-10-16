FROM python:3.13-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g nodemon

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r requirements.txt
RUN mkdir /config

ADD . .

# Nodemon automatically detects nodemon.json in /app
CMD ["nodemon", "--config", "nodemon.json", "--exec", "python3 -u intg-hyperion/driver.py"]