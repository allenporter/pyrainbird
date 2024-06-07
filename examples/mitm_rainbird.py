"""
An mitmproxy Addon for rainbird traffic.

See https://docs.mitmproxy.org/stable/addons-overview/ for more technical details of
mitm addons.
"""

import json
import logging
import os
from typing import Optional

from mitmproxy import contentviews, flow, http

import pyrainbird
import pyrainbird.encryption
from pyrainbird import rainbird


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
        output = ["--- Raw ---", data]
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
        output.extend(["--- Decrypted ---", decrypted_data])
        json_body = json.loads(decrypted_data)
        if "params" in json_body:
            # Request
            params = json_body["params"]
            output.extend(["--- request params ---", str(params)])
            if params_data := params.get("data"):
                decoded_data = rainbird.decode(params_data)
                output.extend(["--- decoded request data ---", str(decoded_data)])
        elif "result" in json_body:
            # Response
            result = json_body["result"]
            logging.info("response: %s", result)
            output.extend(["--- response result ---", str(result)])
            if result_data := result.get("data"):
                decoded_data = rainbird.decode(result_data)
                output.extend(["--- decoded response data ---", str(decoded_data)])

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
        assert isinstance(flow, http.HTTPFlow)
        if flow.request:
            if "/stick" in flow.request.path:
                return 1
        return 0


view = DecodeRainbirdView()


def load(_l):
    contentviews.add(view)


def done():
    contentviews.remove(view)
