import json
import datetime
#from pyppeteer import launch
import asyncio
import tornado.web
from tornado.ioloop import IOLoop
from tornado.platform.asyncio import AsyncIOMainLoop
import traceback
import re
from tornado.httputil import HTTPHeaders
from urllib.parse import urlparse,urlunparse
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    AsyncIOMainLoop().install()
except:
    pass
import logging
logging.basicConfig(format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S',level=logging.INFO)
#import config


class ForwordProxy():
    def __init__(self,loop,port):
        self.loop = loop
        self.port = port
    async def pipe(self,reader, writer):
        try:
            while not reader.at_eof():
                data = await reader.read(2048)
                writer.write(data)
                #await writer.drain()
        finally:
            writer.close()

    async def handle_client(self,local_reader, local_writer):
        try:
            data = await local_reader.read(2048)
            #logging.info(data)
            headers = HTTPHeaders.parse(data.decode())
            proxy = re.search(b'injectproxy(.*)injectproxy', data)
            CONNECT = False
            if proxy:
                host,port = urlparse(proxy.group(1).decode()).netloc.split(':')
                print(host,port)
                #去掉设置puppeteer的 "proxy" 头
                data = re.sub(b'injectproxy(.*)injectproxy', b'', data)
            else:
                #判断是否是https而且不使用代理服务器
                if data.startswith(b'CONNECT'):
                    CONNECT = True
                dest = headers.get('Host')
                host, port = dest.split(':') if ':' in dest  else (dest,80)
                #host, port = "127.0.0.1",1080
            #如果使用代理，或者不使用代理而且是http请求则直接连接代理或者目标服务器
            remote_reader, remote_writer = await asyncio.open_connection(host, port,loop=self.loop,ssl=False)
            if CONNECT:
                #如果是https且不使用代理服务器，直接响应200请求给puppeteer
                local_writer.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
            else:
                remote_writer.write(data)
            #await remote_writer.drain()

            pipe1 = self.pipe(local_reader, remote_writer)
            pipe2 = self.pipe(remote_reader, local_writer)
            await asyncio.gather(pipe1, pipe2,loop=self.loop)
        finally:
            local_writer.close()
    def start(self):
        coro = asyncio.start_server(self.handle_client, '127.0.0.1', self.port,loop=self.loop,backlog=5000)
        #asyncio.ensure_future(coro)
        self.loop.run_until_complete(coro)

def run():
    loop = asyncio.new_event_loop()
    fp=ForwordProxy(loop,8888)
    fp.start()
    loop.run_forever()

if __name__ == '__main__':
    run()