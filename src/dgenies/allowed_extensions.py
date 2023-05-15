import os.path
import inspect
import logging
import yaml
from pathlib import Path
from dgenies.lib.decorators import Singleton


@Singleton
class AllowedExtensions:
    """
    Get allowed extensions per job
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.app_dir = os.path.dirname(inspect.getfile(self.__class__))

        # register the tag handler to join list
        yaml.add_constructor('!join', self.join)

        app_dir = os.path.abspath(os.path.dirname(__file__))
        config_search_path = (
            os.path.join(str(Path.home()), ".dgenies", "allowed_extensions.yaml"),
            os.path.join(str(Path.home()), ".dgenies", "allowed_extensions.yaml.local"),
            "/etc/dgenies/allowed_extensions.yaml",
            "/etc/dgenies/allowed_extensions.yaml.local",
            os.path.join(app_dir, "..", "etc", "dgenies", "allowed_extensions.yaml"),
            os.path.join(app_dir, "allowed_extensions.yaml"),
        )

        allowed_ext_file = None
        for f in config_search_path:
            if os.path.exists(f) and os.path.isfile(f):
                allowed_ext_file = f
                break
        if allowed_ext_file is None:
            raise Exception("Configuration file allowed_extensions.yaml not found")

        self.logger.info("Loading {}".format(allowed_ext_file))
        with open(allowed_ext_file, "r") as yaml_stream:
            extensions = yaml.load(yaml_stream, Loader=yaml.Loader)

        self._allowed_extensions_per_format = {k: v['extensions'] for k, v in extensions['formats'].items()}
        self._allowed_formats = extensions['formats']
        self._allowed_formats_per_role = extensions['job']

    @staticmethod
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

    @property
    def allowed_extensions_per_format(self):
        """
        Get the list of file extensions allowed for each file format (e.g. backup: [tar, tar.gz])

        :return: A mapping between format and extensions
        :rtype: dict
        """
        return self._allowed_extensions_per_format

    def get_extensions(self, file_format: str):
        """
        Get the list of extensions allowed for given file format (e.g. [tar, tar.gz] for backup)

        :param file_format: the file format (e.g. fasta, idx, ...)
        :type file_format: str
        :return: Allowed extensions
        :rtype: list of str
        """
        return self._allowed_formats[file_format]["extensions"]

    def get_description(self, file_format: str):
        """
        Get description of file format.

        :param file_format: the file format (e.g. fasta, idx, ...)
        :type file_format: str
        :return: The description if defined, else "a valid file"
        :rtype: str
        """
        return self._allowed_formats[file_format].get("description", "a valid file")

    def get_formats(self, job_type: str, file_role: str):
        """
        Get formats allowed for a given role and given job type.

        :param job_type: The type of job
        :type job_type: str
        :param file_role: The role of file (query, target, align, ...)
        :type file_role: str
        :return: The allowed formats
        :rtype: list of str
        """
        return self._allowed_formats_per_role.get(job_type, dict()).get(file_role, [])

    def get_roles(self, job_type: str):
        """
        For given job type, get roles where a file is expected

        :param job_type: The type of job
        :type job_type: str
        :return: The roles
        :rtype: list of str
        """
        return self._allowed_formats_per_role.get(job_type, dict()).keys()
