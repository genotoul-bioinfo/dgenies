import os
import sys
from setuptools import setup, find_packages
from pathlib import Path

with open('requirements.txt') as f:
    install_reqs = f.read().strip().split('\n')
version = '1.3.0'

if os.name == "posix":

    config_dir = '/etc/dgenies'
    wsgi_dir = '/var/www/dgenies'
    if '--user' in sys.argv:
        config_dir = os.path.join(str(Path.home()), ".dgenies")
        wsgi_dir = config_dir

    data_files = [(config_dir, ['application.properties']),
                  (config_dir, ['tools.yaml']),
                  (wsgi_dir, ['dgenies.wsgi'])]

    if "readthedoc" in sys.executable:
        data_files = []

    setup(
        name='dgenies',
        version=version,
        packages=find_packages('src'),
        package_dir={'dgenies': 'src/dgenies'},
        include_package_data=True,
        zip_safe=False,
        install_requires=install_reqs,
        data_files=data_files,
        scripts=['src/bin/dgenies'],
    )

else:

    setup(
        name='dgenies',
        version=version,
        packages=find_packages('src'),
        package_dir={'dgenies': 'src/dgenies'},
        include_package_data=True,
        zip_safe=False,
        install_requires=install_reqs,
        data_files=[('.dgenies', ['application.properties'])],
        scripts=['src/bin/dgenies'],
    )
