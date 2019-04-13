FROM python:3.6
RUN mkdir -p /opt/
WORKDIR /opt
RUN git clone -b pyppeteer https://github.com/nqzhang/pyspider
WORKDIR /opt/pyspider
RUN pip3.6 install -r requirements.txt
EXPOSE 22224
CMD ["python", "puppeteer_fetcher.py"]