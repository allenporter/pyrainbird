import json
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
        self.rainbird_server = host
        self.rainbird_password = password

    def request(self, data, length):
        request_id = time.time()
        send_data = (
            '{"id":%d,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"%s","length":%d}}'
            % (request_id, data, length)
        )
        for i in range(0, self.retry):
            self.logger.debug(
                "Sending %s to %s, %d. try."
                % (send_data, self.rainbird_server, i + 1)
            )
            try:
                resp = requests.post(
                    "http://%s/stick" % self.rainbird_server,
                    encryption.encrypt(send_data, self.rainbird_password),
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
                decrypted_data = (
                    encryption.decrypt(resp.content, self.rainbird_password)
                    .decode("UTF-8")
                    .rstrip("\x10")
                    .rstrip("\x0A")
                    .rstrip("\x00")
                    .rstrip()
                )
                self.logger.debug("Response: %s" % decrypted_data)
                return json.loads(decrypted_data)["result"]["data"]
            time.sleep(self.retry_sleep)
            continue
