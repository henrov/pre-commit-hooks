from setuptools import setup
import distutils.text_file
from pathlib import Path


def _parse_requirements(filename):
    """Return requirements from requirements file."""
    # Ref: https://stackoverflow.com/a/42033122/
    return distutils.text_file.TextFile(filename=str(Path(__file__).with_name(filename))).readlines()


setup(install_requires=_parse_requirements('requirements.txt'))
