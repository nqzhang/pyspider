const express = require("express");
const puppeteer = require('puppeteer');
const bodyParser = require('body-parser');
const ProxyChain = require('proxy-chain');

const app = express();

app.use(bodyParser.json());
app.use(bodyParser.urlencoded({extended: false}));

let init_browser = true;
let browser_settings = {};

app.use(async (req, res, next) => {
    if (init_browser) {
        var options = req.body;
        /***
        if (options.proxy) {
            if (options.proxy.indexOf("://") == -1) {
                options.proxy = "http://" + options.proxy;
            }
            browser_settings["args"] = ['--no-sandbox', "--disable-setuid-sandbox", "--proxy-server="+options.proxy];
        } else {
          browser_settings["args"] = ['--no-sandbox', "--disable-setuid-sandbox"];
        }
         ***/
        browser_settings["args"] = ['--no-sandbox', "--disable-setuid-sandbox","--proxy-server=127.0.0.1:22223"];
        //console.log(options)
        //browser_settings["headless"] = options.headless
        browser_settings["headless"] = true
        browser = await puppeteer.launch(browser_settings);
        init_browser=false;
        console.log("init browser success!");
        next();
    } else {
        next();
    };
});
    async function autoScroll(page,kiwi_var){
        await page.evaluate(async (kiwi_var) => {
            await new Promise((resolve, reject) => {
                var totalScrolld = 0;
                var distance = document.documentElement.clientHeight;
                var timer = setInterval(() => {
                    var scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalScrolld += 1;
                    if(totalScrolld >= kiwi_var['scrool_times']){
                        clearInterval(timer);
                        resolve();
                    }
                }, kiwi_var['scrool_wait']);
            });
        },kiwi_var);
}
async function fetch(options) {
    var page = await browser.newPage();
    options.start_time = Date.now();
    try {
        await _fetch(page, options);
        var result = await make_result(page, options);
        await page.close();
        return result
    } catch (error) {
        console.log('catch error ', error);
        var result = await make_result(page, options, error);
        await page.close();
        return result
    }
}

async function _fetch(page, options) {

    width = options.js_viewport_width || 1024;
    height = options.js_viewport_height || 768 * 3;
    await page.setViewport({
        "width": width,
        "height": height
    });

    if (options.headers) {
        await page.setExtraHTTPHeaders(options.headers);
    }

    if (options.headers && options.headers["User-Agent"]) {
        page.setUserAgent(options.headers["User-Agent"] + ' realproxy ' + options.proxy);
    }

    //page.on("console", msg => {
     //   console.log('console: ' + msg.args());
    //});

    let disableRequestInterception = options.disable_interception === "true" ? true:false
    //console.log(disableRequestInterception)
    if (!disableRequestInterception) {
        console.log(1111)
        // Http post method
        let first_request = true;
        let request_reseted = false;
        await page.setRequestInterception(true);
        if (options.method && options.method.toLowerCase() === "post") {
            page.on("request", interceptedRequest => {
                request_reseted = false;
                end_time = null;
                if (first_request) {
                    first_request = false;
                    var data = {
                        "method": "POST",
                        "postData": options.data
                    };
                    console.log(data);
                    interceptedRequest.continue(data);
                    request_reseted = true
                }
            })
        } else {
            page.on("request", interceptedRequest => {
                request_reseted = false;
                end_time = null;
            })
        }

        // load images or not
        let load_images = options.load_images === "true" ? true:false
        if (!load_images) {
            page.on("request", request => {
                if (!!!request_reseted) {
                    resource_type = request.resourceType()
                    if (resource_type === 'image' || request.resourceType() === 'stylesheet'
                        || resource_type === 'media' || resource_type === 'font' || resource_type === 'media'
                    )
                        request.abort();
                    else
                        request.continue();
                }
            })
        } else {
            page.on("request", request => {
                if (!!!request_reseted)
                    request.continue()
            })
        }


    }
    let error_message = null;
    page.on("error", e => {
        error_message = e
    });
    let page_settings = {};
    var page_timeout = options.timeout ? options.timeout * 1000 : 20 * 1000;
    page_settings["timeout"] = page_timeout
    page_settings["waitUntil"] = ["domcontentloaded"];

    console.log('goto ', options.url)
    var response = await page.goto(options.url, page_settings);
    await page.setContent((await response.buffer()).toString('utf8'));
    if (options.kiwi_var) {
        var kiwi_var = options.kiwi_var
        if (kiwi_var['scrool_times']) {
            kiwi_var['scrool_wait'] = kiwi_var['scrool_wait'] ? kiwi_var['scrool_wait'] : 500;
            console.log(kiwi_var)
            await autoScroll(page, kiwi_var);
        }

    }
    if (error_message) {
        throw error_message
    }

    if (options.js_script) {
        console.log('running document-end script.');
        script_result = await page.evaluate(options.js_script);
        console.log("end script_result is: ", script_result);
        options.script_result = script_result
    }

    if (options.screenshot_path) {
        await page.screenshot({path: options.screenshot_path});
    }

    options.response = response
}

async function make_result(page, options, error) {
    response = options.response;

    var cookies = {};
    var tmp_cookies = await page.cookies();
    tmp_cookies.forEach(function (e) {
        cookies[e.name] = e.value;
    });

    let status_code = null;
    let headers = null;
    let page_content = null;

    if (!!!error) {
        response = options.response;
        status_code = response.status();
        headers = response.headers();
        page_content = await page.content();
    }

    return {
        orig_url: options.url,
        status_code: status_code || 599,
        error: error,
        content: page_content,
        headers: headers,
        url: page.url(),
        cookies: cookies,
        time: (Date.now() - options.start_time) / 1000,
        js_script_result: options.script_result,
        save: options.save
    }
}

app.get("/", function (request, response) {
    body = "method not allowed!";
    response.status(403);
    response.set({
        "cache": "no-cache",
        "Content-Length": body.length
    });
    response.send(body);
});



let max_open_pages = 20;
let opened_page_nums = 0;

app.post("/", async (request, response) => {
    console.log("opened pages: " + opened_page_nums);
    if (opened_page_nums >= max_open_pages){
        body = "browser pages is too many, open new browser process!";
        response.status(403);
        response.set({
            "cache": "no-cache",
            "Content-Length": body.length
        });
        response.send(body);
    } else {
        opened_page_nums += 1;
        let options = request.body;
        result = await fetch(options);
        opened_page_nums -= 1;
        response.send(result)
    }
});

const ProxyChainServer = new ProxyChain.Server({
  // Port where the server the server will listen. By default 8000.
  port: 22223,

  // Enables verbose logging
  verbose: false,

  prepareRequestFunction: ({
    request
  }) => {
    let upstreamProxyUrl;
    useragent = request.headers['user-agent'];
    real_useragent = useragent.split(' realproxy ')[0];
      real_proxy = useragent.split(' realproxy ')[1];
      request.headers['user-agent'] = real_useragent;
    if (real_proxy) upstreamProxyUrl = real_proxy;
    return { upstreamProxyUrl };
  },
});

ProxyChainServer.listen(() => {
  console.log(`Router Proxy server is listening on port ${22223}`);
});

let port = 22222;

if (process.argv.length === 3) {
    port = parseInt(process.argv[2])
}

app.listen(port, function () {
    console.log("puppeteer fetcher running on port " + port);
});
