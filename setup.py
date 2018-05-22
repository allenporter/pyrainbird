try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(

    name='pyrainbird',
    version='0.1.5',
    description='Rain Bird Controller',

    install_requires=['pycrypto'],

    packages=['pyrainbird'],

    #The project's main homepage.
    url='https://github.com/jbarrancos/pyrainbird/',

    # Author details
    author='J.J.Barrancos',
    author_email='jordy@fusion-ict.nl',

    license='MIT',

    keywords = ['Rain Bird'],
    classifiers=[],
    zip_safe=True

)
