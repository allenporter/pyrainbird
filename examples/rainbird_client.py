#!/usr/bin/env python3
import sys

from pyrainbird import RainbirdController
import logging
import os

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
ch.setFormatter(formatter)
logger.addHandler(ch)

logging.getLogger().setLevel(logging.DEBUG)
requests_log = logging.getLogger("http.client")
requests_log.setLevel(logging.DEBUG)
requests_log.propagate = True
requests_log.addHandler(ch)

controller = RainbirdController(
    os.environ["RAINBIRD_SERVER"], os.environ["RAINBIRD_PASSWORD"]
)
print("%s\n" % controller.command(sys.argv[1], *sys.argv[2:]))
