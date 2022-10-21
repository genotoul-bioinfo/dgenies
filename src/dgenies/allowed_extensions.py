import os.path
import yaml
from pathlib import Path


def join(loader, node):
    """
    Merge yaml sequence nodes as a list

    :param loader: yaml loader
    :type loader: Loader
    :param node: yaml node
    :type node: Node
    :return: list of Nodes
    """
    seq = loader.construct_sequence(node)
    return [e for l in seq for e in l]


# register the tag handler to join list
yaml.add_constructor('!join', join)

app_dir = os.path.abspath(os.path.dirname(__file__))
config_search_path = (
    os.path.join(str(Path.home()), ".dgenies", "allowed_extensions.yaml"),
    os.path.join(str(Path.home()), ".dgenies", "allowed_extensions.yaml.local"),
    "/etc/dgenies/allowed_extensions.yaml",
    "/etc/dgenies/allowed_extensions.yaml.local",
    os.path.join(app_dir, "allowed_extensions.yaml"),
)

allowed_ext_file = None
for f in config_search_path:
    if os.path.exists(f) and os.path.isfile(f):
        allowed_ext_file = f
        break
if allowed_ext_file is None:
    raise Exception("Configuration file allowed_extensions.yaml not found")

with open(allowed_ext_file, "r") as yaml_stream:
    extensions = yaml.load(yaml_stream, Loader=yaml.Loader)

ALLOWED_GROUPED_EXTENSIONS = extensions['groups']
ALLOWED_FILE_EXTENSIONS = extensions['server']
