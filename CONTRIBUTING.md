# Contributing

## Setup a virtual environment

```
$ python3 -m venv venv
$ source venv/bin/activate
$ pip3 install -r requirements_dev.txt
```

## Running the tests

```
$ pytest
```

## Running mitmproxy

You may use mitmproxy to inspect and decode responses. To run mitmproxy
with the decoder plugin:

```
$ export RAINBIRD_PASSWORD="mypass"
$ mitmproxy -s examples/mitm_rainbird.py
```
