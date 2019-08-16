#!/usr/bin/env python3

from pyrainbird import RainbirdController
import logging
import os

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

controller = RainbirdController(os.environ['RAINBIRD_SERVER'], os.environ['RAINBIRD_PASSWORD'])
#print('%s\n' % controller.command(sys.argv[1], *sys.argv[2:]))
print('%s\n' % controller.startIrrigation(5, 1))
print('%s\n' % controller.currentIrrigation())
print('%s\n' % controller.startIrrigation(6, 1))
print('%s\n' % controller.currentIrrigation())
print('%s\n' % controller.stopIrrigation())
print('%s\n' % controller.currentIrrigation())
print('%s\n' % controller.currentRainSensorState())

