FROM python:3.11-slim-bullseye
WORKDIR /app

# Install nodemon for auto-reload on file changes
RUN apt-get update && apt-get install -y npm && npm install -g nodemon

COPY ./requirements.txt requirements.txt
RUN pip3 install --no-cache-dir --upgrade -r requirements.txt

ADD . .

# TODO: Update the path if you rename the intg-hyperion folder
CMD ["python3", "-u", "intg-hyperion/driver.py"]