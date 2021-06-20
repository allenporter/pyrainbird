import json

from pkg_resources import resource_string

# parameters in number of nibbles (based on string representations of SIP bytes), total lengths in number of SIP bytes

# Changed in json version 3.9: The keyword argument encoding has been removed.
# https://docs.python.org/3/library/json.html
RAIBIRD_COMMANDS = json.loads(resource_string('pyrainbird.resources', 'sipcommands.json').decode("UTF-8"))
