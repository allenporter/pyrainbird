import http.client
import json
import time
import logging
from . import encryption

HEAD = {
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "RainBird/2.0 CFNetwork/811.5.4 Darwin/16.7.0",
    "Accept": "*/*",
    "Connection": "keep-alive"}


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
            resp = self._send_rainbird_command(senddata)
            if resp is None or resp.status != 200:
                time.sleep(self.retry_sleep)
                continue
            else:
                decrypteddata = encryption.decrypt(resp.read(), self.rainbirdPassword).decode("UTF-8").rstrip('\x00')
                self.logger.debug('Response: %s' % decrypteddata)
                return json.loads(decrypteddata)["result"]["data"]

    def _send_rainbird_command(self, senddata):
        try:
            h = http.client.HTTPConnection(self.rainbirdServer, 80, timeout=20)
            h.request("POST", "/stick", encryption.encrypt(senddata,
                                                           self.rainbirdPassword), HEAD)
            return h.getresponse()
        except Exception as e:
            self.logger.warn('Unable to connect: %s' % e)
            return None
        finally:
            h.close()
