import json
import yaml

from pkg_resources import resource_string, resource_stream

# parameters in number of nibbles (based on string representations of SIP bytes), total lengths in number of SIP bytes

# Changed in json version 3.9: The keyword argument encoding has been removed.
# https://docs.python.org/3/library/json.html
RAIBIRD_COMMANDS = json.loads(resource_string('pyrainbird.resources', 'sipcommands.json').decode("UTF-8"))
RAIBIRD_MODELS = yaml.load(resource_stream('pyrainbird.resources', 'models.yaml').decode("UTF-8"))
