import shlex
import sys

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand

with open("requirements.txt") as fd:
    requirements = [line.rstrip() for line in fd]

with open("test_requirements.txt") as fd:
    test_requirements = [line.rstrip() for line in fd]


class PyTest(TestCommand):
    user_options = [("pytest-args=", "a", "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ""

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest

        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


setup(
    name="pyrainbird",
    version="0.5.0",
    description="Rain Bird Controller",
    install_requires=requirements,
    tests_require=test_requirements,
    # The project's main homepage.
    url="https://github.com/jbarrancos/pyrainbird/",
    # Author details
    author="J.J.Barrancos",
    author_email="jordy@fusion-ict.nl",
    license="MIT",
    keywords=["Rain Bird"],
    classifiers=[],
    zip_safe=True,
    cmdclass={"test": PyTest},
    packages=find_packages(exclude=("test", "test.*")),
    package_data={'': ['sipcommands.yaml', 'models.yaml']},
    include_package_data=True,
)
