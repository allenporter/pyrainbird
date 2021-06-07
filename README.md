![](http://iqweb.rainbird.com/iq/images/logos/rainbird.png) 
# pyrainbird ![](https://img.shields.io/badge/python-2+-green.svg) [![Build Status](https://travis-ci.org/konikvranik/pyrainbird.svg?branch=master)](https://travis-ci.org/konikvranik/pyrainbird) [![Coverage Status](https://coveralls.io/repos/github/konikvranik/pyrainbird/badge.svg?branch=master)](https://coveralls.io/github/konikvranik/pyrainbird?branch=master)
> Python module for interacting with WiFi LNK module of the Rain Bird Irrigation system

This project has no affiliation with Rain Bird. This module works with the Rain Bird LNK WiFi Module.
 For more information see https://www.rainbird.com/products/module-wi-fi-lnk

----

This module communicates directly towards the IP Address of the WiFi module it does not support the cloud.
 You can start/stop the irrigation and get the currently active zone.

I'm not a Python developer, so sorry for the bad code. I've developed it to control it from my domtica systems.


**Please, feel free to contribute to this repo or chip in some cents for the effort and [![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=TFXBL7W9VEQZC)

On the bottom of the module is some test code. Feel free te test it with your own

```python

# Test for controller
from pyrainbird import RainbirdController
import time
import logging

logging.basicConfig(filename='pypython.log',level=logging.DEBUG)


_LOGGER = logging.getLogger(__name__)
_LOGGER .setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
_LOGGER.addHandler(ch)

controller = RainbirdController("####IP#####","####PASS#####")
controller.irrigate_zone(4,5)
time.sleep(4)
controller.stop_irrigation()

```
