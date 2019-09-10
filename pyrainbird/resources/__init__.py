import json

from pkg_resources import resource_string

# parameters in number of nibbles (based on string representations of SIP bytes), total lengths in number of SIP bytes
RAIBIRD_COMMANDS = json.loads(resource_string('pyrainbird.resources', 'sipcommands.json').decode("UTF-8"),
                              encoding="UTF-8")
