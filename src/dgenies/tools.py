import os
import sys
import re
import inspect
from pathlib import Path
import yaml
from dgenies.lib.decorators import Singleton
from dgenies.lib import parsers


class Tool:

    def __init__(self, name, exec, command_line, all_vs_all, max_memory, label=None, threads=1, exec_cluster=None,
                 threads_cluster=None, parser=None, split_before=False, help=None, order=None, options=None):
        """
        Create a new tool

        :param command_line: command line to launch the tool
        :param all_vs_all: command line in all_vs_all mode (None if not available for the tool)
        :param max_memory: max memory the tool is supposed to use (ex: 40G) - for cluster submissions
        :param label: Name to display for user
        :param parser: name of the function in dgenies.lib.functions to launch after mapping to have a correct PAF out
            file
        :param split_before: True to split contigs before mapping
        :type split_before: bool
        :param help: help message to show in run form
        :param order: order to show in run mode
        :param options: list of options for the tool
        """
        # Name
        self.name = name

        # Label
        if label:
            self.label = label
        else:
            self.label = name

        # Exec
        if exec == "default":
            self.exec = os.path.join(os.path.dirname(inspect.getfile(self.__class__)), "bin", self.name)
        else:
            self.exec = exec.replace("###SYSEXEC###", os.path.dirname(sys.executable))
        if exec_cluster is None or exec_cluster == "default":
            self.exec_cluster = exec
        else:
            self.exec_cluster = exec_cluster.replace("###SYSEXEC###", os.path.dirname(sys.executable))

        # Command line:
        if "{exe}" in command_line and "{target}" in command_line and "{query}" in command_line and "{out}" \
                in command_line:
            self.command_line = command_line
        else:
            raise ValueError("Tools: command_line must contains at least {exe}, {target}, {query} and {out} tags")

        # All_vs_all:
        if all_vs_all is None or ("{exe}" in all_vs_all and "{target}" in all_vs_all and "{out}" in all_vs_all):
            self.all_vs_all = all_vs_all
        else:
            raise ValueError("Tools: all_vs_all must contains at least {exe}, {target} and {out} tags")

        # Max memory:
        if max_memory is None or isinstance(max_memory, int):
            self.max_memory = max_memory
        else:
            raise ValueError("Tools: max_memory must be an integer, or !!null")

        # Threads:
        if isinstance(threads, int):
            self.threads = threads
        else:
            raise ValueError("Tools: threads must be an integer")
        if threads_cluster is None or isinstance(threads_cluster, int):
            if threads_cluster is None:
                self.threads_cluster = self.threads
            else:
                self.threads_cluster = threads_cluster
        else:
            raise ValueError("Tools: threads_cluster must be an integer, or !!null")

        # Parser:
        if parser is None or hasattr(parsers, parser):
            self.parser = parser
        else:
            raise ValueError("Tools: parser %s is not defines in dgenies.lib.parsers!" % parser)

        # split_before:
        if isinstance(split_before, bool):
            self.split_before = split_before
        else:
            raise ValueError("Tools: split_before must be a boolean (True or False)")

        # Help:
        self.help = help

        # Order:
        if order is None or isinstance(order, int):
            if order is None:
                self.order = 1000
            else:
                self.order = order

        # Options
        if options is None or isinstance(options, list):
            self.options = options
        else:
            raise ValueError("Tools: options must be a yaml list")



@Singleton
class Tools:
    """
    Load (from yaml file) and store available alignment tools
    """

    def __init__(self):
        self.tools = {}
        self.load_yaml(trusted=True)

    def load_yaml(self, trusted=False):
        app_dir = os.path.dirname(inspect.getfile(self.__class__))
        yaml_file = None
        config_file_search = [os.path.join(os.path.abspath(os.sep), "dgenies", "tools.yaml"),
                              "/etc/dgenies/tools.yaml",
                              "/etc/dgenies/tools.yaml.local",
                              os.path.join(str(Path.home()), ".dgenies", "tools.yaml"),
                              os.path.join(str(Path.home()), ".dgenies", "tools.yaml.local"),
                              os.path.join(app_dir, '..', 'etc', 'dgenies', 'tools.yaml')]

        if os.name == "nt":
            config_file_search.insert(1, os.path.join(sys.executable, '..', "tools.yaml"))
            config_file_search.insert(1, os.path.join(sys.executable, '..', "tools.yaml.local"))

        config_file_search.append(os.path.join(app_dir, "tools-dev.yaml"))
        config_file_search.append(os.path.join(app_dir, "tools-dev.yaml.local"))

        for my_config_file in reversed(config_file_search):
            if os.path.exists(my_config_file):
                yaml_file = my_config_file
                break
        if yaml_file is None:
            raise FileNotFoundError("ERROR: tools.yaml not found.")

        with open(yaml_file, "r") as yml_f:
            tools_dict = yaml.load(yml_f, Loader=yaml.FullLoader if trusted else yaml.SafeLoader)
            tools = {}
            for name, props in tools_dict.items():
                tools[name] = Tool(name=name, **props)
            self.tools.update(tools)
