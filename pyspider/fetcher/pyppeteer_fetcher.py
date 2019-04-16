import json
import datetime
from pyppeteer import launch
import asyncio
import tornado.web
from tornado.ioloop import IOLoop
from tornado.platform.asyncio import AsyncIOMainLoop
import traceback
import re,os
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

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", PostHandler),
        ]
        super(Application, self).__init__(handlers, settings = {"debug": False,"autoreload": False,})
    def init_browser(self, loop):
       self.browser = loop.run_until_complete(run_browser())

async def run_browser():
    browser_settings = {}
    #browser_settings['executablePath'] = 'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
    browser_settings["headless"] = False
    browser_settings['devtools'] = False
    browser_settings['autoClose'] = True
    browser_settings['ignoreHTTPSErrors'] = True
    # 在浏览器级别设置本地代理
    if env == "production":
        browser_settings['executablePath'] = '/usr/bin/google-chrome-stable'
        browser_settings["headless"] = True
    browser_settings["args"] = ['--no-sandbox', "--disable-setuid-sandbox","--disable-gpu"];
    browser =  await launch(browser_settings)
    return browser

def _parse_cookie(cookie_list):
    if cookie_list:
        cookie_dict = dict()
        for item in cookie_list:
            cookie_dict[item['name']] = item['value']
        return cookie_dict
    return {}

class PostHandler(tornado.web.RequestHandler):
    async def _fetch(self,fetch):
        async def request_check(req):
            if req.resourceType == 'image':
                await req.abort()

            else:
                headers = req.headers
                if proxy:
                    fetch['headers']['proxy'] = proxy
                    headers.update(fetch['headers'])
                    # 通过在header设置 "proxy" 头供代理服务器连接接真实代理服务器，代理服务器发出请求时去掉这个头
                    await req.continue_(overrides={"headers":headers})
                else:
                    await req.continue_()

        result = {'orig_url': fetch['url'],
                  'status_code': 200,
                  'error': '',
                  'content': '',
                  'headers': {},
                  'url': '',
                  'cookies': {},
                  'time': 0,
                  'js_script_result': '',
                  'save': '' if fetch.get('save') is None else fetch.get('save')
                  }
        try:
            browser = self.application.browser
            start_time = datetime.datetime.now()

            page = await browser.newPage()
            await page.evaluateOnNewDocument('''() => {
                  Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                  });
                }''')
            proxy = fetch.get('proxy',None)

            #print(fetch['headers'])
            #await page.setExtraHTTPHeaders(fetch['headers'])
            await page.setUserAgent(fetch['headers']['User-Agent'])
            page_settings = {}
            page_settings["waitUntil"] = ["domcontentloaded","networkidle2"]
            page_settings["timeout"] = fetch['timeout'] * 1000
            #print(page_settings["timeout"])
            await page.setRequestInterception(True)
            page.on('request',lambda req:asyncio.ensure_future(request_check(req)))
            response = await page.goto(fetch['url'], page_settings)

            result['content'] = await page.content()
            result['url'] = page.url
            result['status_code'] = response.status
            result['cookies'] = _parse_cookie(await page.cookies())
            result['headers'] = response.headers
            end_time = datetime.datetime.now()
            result['time'] = (end_time - start_time).total_seconds()
        except Exception as e:
            result['error'] = str(e)
            result['status_code'] = 599
            traceback.print_exc()
        finally:
            #pass
            await page.close()
        #print('result=', result)
        return result
    async def get(self, *args, **kwargs):
        body = "method not allowed!"
        self.set_header('cache-control','no-cache,no-store')
        self.set_header('Content-Length',len(body))
        self.set_status(403)
        self.write(body)
    async def post(self, *args, **kwargs):
        raw_data = self.request.body.decode('utf8')
        fetch = json.loads(raw_data, encoding='utf-8')
        result = await self._fetch(fetch)
        logging.info('{} {}'.format(fetch['url'],result['status_code']))
        #print(result)
        self.write(result)
class ForwordProxy():
    def __init__(self,loop,port):
        self.loop = loop
        self.port = port
    async def pipe(self,reader, writer):
        try:
            while not reader.at_eof():
                data = await reader.read(2048)
                writer.write(data)
        except (ConnectionError,RuntimeError) as e:
            pass
            #logging.warning(f"connection was reset; {e}")
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
                regex = re.compile(b"^http://|^https://|^socks5://")
                host,port = regex.sub(b'',proxy.group(1)).split(b":")
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
            fut = asyncio.open_connection(host, port,loop=self.loop,ssl=False)
            try:
                remote_reader, remote_writer = await asyncio.wait_for(fut, timeout=3)
            except (asyncio.TimeoutError,ConnectionRefusedError):
                return
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
        if env == 'production':
            coro = asyncio.start_server(self.handle_client, '127.0.0.1', self.port,loop=self.loop,backlog=5000,reuse_address=True,reuse_port=True)
        else:
            coro = asyncio.start_server(self.handle_client, '127.0.0.1', self.port, loop=self.loop)
        #asyncio.ensure_future(coro)
        self.loop.run_until_complete(coro)

def run():
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'../../config.json')) as f:
        config = json.load(f)
    global env
    env = config.get('env','production')
    loop = asyncio.get_event_loop()
    #在本地启动一个代理服务器
    fp=ForwordProxy(loop,8888)
    fp.start()
    app = Application()
    app.init_browser(loop)
    app.listen(8071)
    loop.run_forever()

if __name__ == '__main__':
    run()
