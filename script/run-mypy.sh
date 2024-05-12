#!/usr/bin/env bash

set -o errexit


pip3 install -r requirements_dev.txt --no-input --quiet

mypy .
