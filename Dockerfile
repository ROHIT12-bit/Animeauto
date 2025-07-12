FROM python:3.10-slim-buster

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

RUN apt update && apt install -y ffmpeg
RUN apt-get update && apt-get upgrade -y
RUN apt-get install git wget pv jq python3-dev mediainfo gcc libsm6 libxext6 libfontconfig1 libxrender1 libgl1-mesa-glx -y

RUN pip install lxml_html_clean

COPY --from=mwader/static-ffmpeg:6.1 /ffmpeg /bin/ffmpeg
COPY --from=mwader/static-ffmpeg:6.1 /ffprobe /bin/ffprobe

COPY . .
RUN pip3 install --no-cache-dir -r requirements.txt

RUN pip install "lxml[html_clean]"

CMD ["bash","run.sh"]
