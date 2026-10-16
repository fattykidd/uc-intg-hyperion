FROM python:3.13-slim
WORKDIR /app

# Install Node.js, npm, and nodemon for auto-reload on file changes
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g nodemon

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r requirements.txt
RUN mkdir /config

ADD . .

# Run via nodemon so it auto-restarts only when your Python files change
CMD ["nodemon", "--ext", "py", "--exec", "python3", "-u", "intg-hyperion/driver.py"]