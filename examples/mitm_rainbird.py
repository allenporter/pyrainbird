"""
An mitmproxy Addon for rainbird traffic.

See https://docs.mitmproxy.org/stable/addons-overview/ for more technical details of
mitm addons.
"""

import gzip
import json
import logging
from typing import Optional, Iterable
import os

import pyrainbird

from mitmproxy import contentviews, flow
from mitmproxy import http


class DecodeRainbirdView(contentviews.View):
    name = "rainbird"

    def __call__(
        self,
        data: bytes,
        *,
        content_type: Optional[str] = None,
        flow: Optional[flow.Flow] = None,
        http_message: Optional[http.Message] = None,
        **unknown_metadata,
    ) -> contentviews.TViewResult:

        logging.debug("raw %s", data)
        output = [
            "--- Raw ---",
            data
        ]
        passwd = os.environ["RAINBIRD_PASSWORD"]
        decrypted_data = (
            pyrainbird.encryption.decrypt(data, passwd)
            .decode("UTF-8")
            .rstrip("\x10")
            .rstrip("\x0A")
            .rstrip("\x00")
            .rstrip()
        )
        logging.debug("decrypted %s", decrypted_data)
        output.extend([
            "--- Decrypted ---",
            decrypted_data
        ])
        json_body = json.loads(decrypted_data)
        if "params" in json_body:
            # Request
            params = json_body["params"]
            output.extend([
                "--- request params ---",
                str(params)
            ])
        elif "result" in json_body:
            # Response
            result = json_body["result"]
            logging.info("response: %s", result)
            output.extend([
                "--- response result ---",
                str(result)
            ])

        def result():
            for row in output:
                logging.info("yielding: %s", row)
                yield [("text", row)]

        return "rainbird", result()

    def render_priority(
        self,
        data: bytes,
        *,
        content_type: Optional[str] = None,
        flow: Optional[flow.Flow] = None,
        http_message: Optional[http.Message] = None,
        **unknown_metadata,
    ) -> float:
        if not content_type or not http_message:
            return 0
        if content_type != "application/octet-stream":
            return 0
        if flow.request: 
            if "/stick" in flow.request.path:
                return 1
        return 0


view = DecodeRainbirdView()


def load(l):
    contentviews.add(view)

def done():
    contentviews.remove(view)
