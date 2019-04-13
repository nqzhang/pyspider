FROM centos/python-36-centos7
RUN mkdir -p /opt/pyspider
WORKDIR "/opt/pyspider"

RUN git clone -b pyppeteer https://github.com/nqzhang/pyspider
pip3.6 install -r requirements.txt