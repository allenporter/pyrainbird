from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
   
    name='pyrainbird',
    version='0.0.6',
    description='Rainbird Controller',
    long_description=long_description,

    packages=find_packages(exclude=('tests', 'docs')),
    
    #The project's main homepage.
    url='https://github.com/jbarrancos/pyrainbird/',

    # Author details
    author='J.J.Barrancos',
    author_email='jordy@fusion-ict.nl',

    license='MIT',

    keywords = ['Rainbird'],
    classifiers=[],


)