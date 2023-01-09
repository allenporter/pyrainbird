from unittest.mock import patch
import requests_mock
import requests
import json

from pyrainbird import RainbirdClient
from pyrainbird import encryption

HOST = "host"
URL = "http://host/stick"
PASSWORD = "password"
REQUEST = "example data"
LENGTH = len(REQUEST)

RESULT_DATA = "result-data"
RESPONSE = json.dumps({
    "result": {
        "data": RESULT_DATA,
    }
})
RESPONSE = encryption.encrypt(RESPONSE, PASSWORD)


def test_request() -> None:
    """Test a basic request."""

    client = RainbirdClient(HOST, PASSWORD, retry=1, retry_sleep=0)

    with requests_mock.mock() as m:
        m.post(URL, content=RESPONSE)

        resp = client.request(REQUEST, LENGTH)

    assert resp == RESULT_DATA


def test_request_failure() -> None:
    """Test a basic request failure handling."""

    client = RainbirdClient(HOST, PASSWORD, retry=2, retry_sleep=0)

    with requests_mock.mock() as m:
        m.post(URL, status_code=500)
        resp = client.request(REQUEST, LENGTH)

    assert resp is None


def test_request_timeout() -> None:
    """Test a timeout while connecting."""

    client = RainbirdClient(HOST, PASSWORD, retry=2, retry_sleep=0)

    with requests_mock.mock() as m:
        m.post(URL, exc=requests.exceptions.ConnectTimeout)
        resp = client.request(REQUEST, LENGTH)

    assert resp is None


def test_request_failure_retry() -> None:
    """Test a failure retry behavior"""

    client = RainbirdClient(HOST, PASSWORD, retry=2, retry_sleep=0)

    with requests_mock.mock() as m:
        m.register_uri('POST', URL, [
            {'status_code': 500},
            {'content': RESPONSE, 'status_code': 200}
        ])
        resp = client.request(REQUEST, LENGTH)

    assert resp == RESULT_DATA
