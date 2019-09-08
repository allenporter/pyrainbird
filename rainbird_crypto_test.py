#!/usr/bin/env python3

from pyrainbird import encryption, RainbirdController
import logging
import os

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

password = "somepassword123"
encrypt = encryption.encrypt(
    '{"id":9,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"02","length":1}}',
    password,
)
print("%s\n" % encrypt)

decrypt = encryption.decrypt(encrypt, password)

print("%s\n" % decrypt)

controller = RainbirdController(
    os.environ["RAINBIRD_SERVER"], os.environ["RAINBIRD_PASSWORD"]
)

print("%s\n" % controller.get_rain_delay())
