# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals
import logging
import random
from .proxy_utils import carregar_proxies
# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class Trf2SpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # maching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class Trf2DownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.info("Spider opened: %s" % spider.name)


class ProxyRotationMiddleware:
    """Selects a random proxy for each request using Webshare proxies."""

    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key
        self.proxies = carregar_proxies(api_url, api_key)

    @classmethod
    def from_crawler(cls, crawler):
        api_url = crawler.settings.get('WEBSHARE_PROXY_URL')
        api_key = crawler.settings.get('WEBSHARE_API_KEY')
        mw = cls(api_url, api_key)
        crawler.signals.connect(mw.spider_opened, signal=signals.spider_opened)
        return mw

    def spider_opened(self, spider):
        spider.logger.info(f"Proxy middleware loaded {len(self.proxies)} proxies")

    def process_request(self, request, spider):
        if 'proxy' in request.meta:
            return

        if not self.proxies:
            spider.logger.error("A lista de proxies está vazia!")
            return

        proxy = random.choice(self.proxies)
        request.meta['proxy'] = proxy
        logging.debug(f"Usando proxy {proxy} para a requisição {request.url}")

    def process_exception(self, request, exception, spider):
        proxy = request.meta.get('proxy')
        if proxy and proxy in self.proxies:
            logging.warning(f"Proxy {proxy} falhou com a exceção: {exception.__class__.__name__}. Removendo da lista.")
            self.proxies.remove(proxy)
            
            # Adiciona o proxy removido a uma lista de retentativa para não perder a requisição
            new_request = request.copy()
            new_request.meta.pop('proxy', None) # Remove o proxy para que seja escolhido um novo
            return new_request
        return None # Deixa outros middlewares de exceção tratarem

