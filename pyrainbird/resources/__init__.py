import yaml
from pkg_resources import resource_stream

# parameters in number of nibbles (based on string representations of SIP bytes), total lengths in number of SIP bytes
RAINBIRD_COMMANDS = yaml.load(
    resource_stream("pyrainbird.resources", "sipcommands.yaml"), Loader=yaml.FullLoader
)
RAINBIRD_MODELS = yaml.load(
    resource_stream("pyrainbird.resources", "models.yaml"), Loader=yaml.FullLoader
)
