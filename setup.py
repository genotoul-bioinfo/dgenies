import os
import sys
from setuptools import setup, find_packages
from pip.req import parse_requirements
from pathlib import Path

install_reqs = parse_requirements('requirements.txt', session='hack')
# reqs is a list of requirement
# e.g. ['django==1.5.1', 'mezzanine==1.4.6']
reqs = [str(ir.req) for ir in install_reqs]
version = '1.1.0'

if os.name == "posix":

    config_dir = '/etc/dgenies'
    wsgi_dir = '/var/www/dgenies'
    if '--user' in sys.argv:
        config_dir = os.path.join(str(Path.home()), ".dgenies")
        wsgi_dir = config_dir

    setup(
        name='dgenies',
        version=version,
        packages=find_packages('src'),
        package_dir={'dgenies': 'src/dgenies'},
        include_package_data=True,
        zip_safe=False,
        install_requires=reqs,
        data_files=[(config_dir, ['application.properties']),
                    (config_dir, ['tools.yaml']),
                    (wsgi_dir, ['dgenies.wsgi'])],
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
        install_requires=reqs,
        data_files=[('.dgenies', ['application.properties'])],
        scripts=['src/bin/dgenies'],
    )
