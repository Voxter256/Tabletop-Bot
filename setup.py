from setuptools import setup

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

setup(
    name="Tabletop-Bot",
    url='https://github.com/Voxter256/Tabletop-Bot',
    packages=['bot'],
    license='MIT License',
    install_requires=requirements,
    long_description=open('README.md').read()
)