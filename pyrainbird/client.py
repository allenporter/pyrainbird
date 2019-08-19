import http.client
import json
import time
import logging
import requests
from . import encryption

HEAD = {
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "RainBird/2.0 CFNetwork/811.5.4 Darwin/16.7.0",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Content-Type": "application/octet-stream"}


class RainbirdClient:

    def __init__(self, host, password, retry=3, retry_sleep=10, logger=logging.getLogger(__name__)):
        self.retry = retry
        self.retry_sleep = retry_sleep
        self.logger = logger
        self.rainbirdServer = host
        self.rainbirdPassword = password

    def request(self, data, length):
        request_id = time.time()
        senddata = '{"id":%d,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"%s","length":%d}}' % (
            request_id, data, length)
        for i in range(0, self.retry):
            self.logger.debug('Sending %s to %s, %d. try.' %
                              (senddata, self.rainbirdServer, i + 1))
            try:
                resp = requests.post("http://%s/stick" % self.rainbirdServer,
                                     encryption.encrypt(senddata, self.rainbirdPassword), headers=HEAD, timeout=20)
            except Exception as e:
                self.logger.warn('Unable to connect: %s' % e)
                resp = None

            if resp is None:
                self.logger.warn("Response not returned.")
            elif resp.status_code != 200:
                self.logger.warn("Response: %d, %s" % (resp.status, resp.reason))
            else:
                decrypteddata = encryption.decrypt(resp.content, self.rainbirdPassword).decode("UTF-8").rstrip('\x00')
                self.logger.debug('Response: %s' % decrypteddata)
                return json.loads(decrypteddata)["result"]["data"]
            time.sleep(self.retry_sleep)
            continue
