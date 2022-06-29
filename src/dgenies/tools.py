import os
import sys
import platform
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
            if sys.platform.startswith('linux') and platform.machine() == 'x86_64':
                # We only provide executable for linux x86_64
                self.exec = os.path.join(os.path.dirname(inspect.getfile(self.__class__)), "bin", self.name)
            else:
                # For other platforms and architectures, we will rely on exec in PATH
                self.exec = self.name
        else:
            # For Windows version
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
            if options is not None:
                self._coord_to_option_value = [[e['value'] for e in o['entries']] for o in options]
        else:
            raise ValueError("Tools: options must be a yaml list")

    @staticmethod
    def _option_key_to_tuple(key: str):
        """
        Transform an option key string into an option key tuple
        :param key: an option key
        :type key: str
        :return: A couple of int (0,0), (0,1), ..., (1,0)
        :rtype: tuple
        """
        i, j = key.split("-", maxsplit=1)
        return int(i), int(j)

    @staticmethod
    def _option_tuple_to_key(t: tuple):
        """
        Transform an option key tuple into an option key string
        :param t: an option key
        :type t: tuple
        :return: return an options keys string like '0-0', '0-1', ..., '1-0'
        :rtype: str
        """
        return "{:d}-{:d}".format(t[0], t[1])

    def get_option_group(self, key):
        """
        Transform an option key string into an option key tuple
        :param key: an option key
        :type key: str or tuple
        :return: the option group coordinate
        :rtype: int
        """
        if isinstance(key, str):
            key = self._option_key_to_tuple(key)
        return key[0]

    def get_default_option_keys(self):
        """
        Get default options keys set for this tool
        :return: A set of options keys like 0-0, 0-1, ..., 1-0
        :rtype: set of str
        """
        default_option_keys = set()
        if self.options is not None:
            for i, o in enumerate(self.options):
                for j, e in enumerate(o['entries']):
                    if e.get("default", False):
                        default_option_keys.add(self._option_tuple_to_key((i, j)))
        return default_option_keys

    def is_valid_option_key(self, key):
        """
        Get default options keys set for this tool
        :param key: an option key
        :type key: str
        :return: True if the option exists for the given key, else False
        :rtype: bool
        """
        try:
            i, j = self._option_key_to_tuple(key)
            self.options[i]["entries"][j]
        except Exception:
            return False
        return True

    def get_option_tuples(self, key=None):
        """
        Get option keys available for this tool.
        :param key: an option key
        :type key: str
        :return: A list of all options keys if key = None, else the list of options keys at the same level than key
        :rtype: set of tuple
        """
        option_key_list = []
        if key is None:
            option_key_list = ((i, j) for i, o in enumerate(self.options) for j, e in enumerate(o["entries"]))
        else:
            i = self._option_key_to_tuple(key)[0]
            # We check the coordinates
            if 0 <= i < len(self.options):
                option_key_list = ((i, j) for j, e in enumerate(self.options[i]["entries"]))
        return list(option_key_list)

    def get_option_keys(self, key=None):
        """
        Get option keys available for this tool.
        :param key: an option key
        :type key: str
        :return: A list of all options keys if key = None, else the list of options keys at the same level than key
        :rtype: set of str
        """
        return [self._option_tuple_to_key(t) for t in self.get_option_tuples(key)]

    def is_an_exclusive_option_key(self, key: str):
        """
        Tells if an option-key (like 0-0, 0-1, ..., 1-0) is a part of an exclusive options
        :return: True if a part of an exclusive option, else false
        :rtype: bool
        """
        group = self.get_option_group(key)
        return self.options[group]["type"] == "radio"

    def resolve_option_keys(self, keys):
        """
        Resolve/Translate options keys like 0-0, 0-1, ..., 1-0, ... to effective parameters
        :param keys: list/set of key
        :type keys: collection of str
        :return: tuple:
            * [0] True if all option keys in keys are valid, False else
            * [1] list of str, associated parameters associated to options keys
        :rtype: tuple
        """
        valid = True
        options_params = []
        try:
            for k in keys:
                o, e = self._option_key_to_tuple(k)
                options_params.append(self._coord_to_option_value[o][e])
        except KeyError:
            valid = False
            options_params = []
        except IndexError:
            valid = False
            options_params = []
        return valid, options_params


@Singleton
class Tools:
    """
    Load (from yaml file) and store available alignment tools
    """

    def __init__(self):
        self.tools = {}
        self.default = None
        self.load_yaml(trusted=True)

    def get_default(self):
        max_order = sys.maxsize
        if self.default is None:
            for n, t in self.tools.items():
                if t.order < max_order:
                    max_order = t.order
                    self.default = n
        return self.default

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
