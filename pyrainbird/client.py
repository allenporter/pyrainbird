import logging
import time

import requests

from . import encryption

HEAD = {
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "RainBird/2.0 CFNetwork/811.5.4 Darwin/16.7.0",
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Content-Type": "application/octet-stream",
}


class RainbirdClient:
    def __init__(
        self,
        host,
        password,
        retry=3,
        retry_sleep=10,
        logger=logging.getLogger(__name__),
    ):
        self.retry = retry
        self.retry_sleep = retry_sleep
        self.logger = logger
        self.rainbird_host = host
        self.coder = encryption.PayloadCoder(password, logger)

    def request(self, data, length):
        payload = self.coder.encode_command(
            "tunnelSip", {"data": data, "length": length}
        )
        for i in range(0, self.retry):
            try:
                resp = requests.post(
                    f"http://{self.rainbird_host}/stick",
                    payload,
                    headers=HEAD,
                    timeout=20,
                )
            except Exception as e:
                self.logger.warning("Unable to connect: %s" % e)
                resp = None

            if resp is None:
                self.logger.warning("Response not returned.")
            elif resp.status_code != 200:
                self.logger.warning(
                    "Response: %d, %s" % (resp.status_code, resp.reason)
                )
            else:
                return self.coder.decode_command(resp.content)["data"]

            time.sleep(self.retry_sleep)
            continue
