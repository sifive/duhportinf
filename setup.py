from setuptools import setup

setup(
    name='abxportinf',
    version='0.1',
    description='library to match flat named port list to library of bus specifications',
    entry_points = {'console_scripts': ['abxportinf=abxportinf.main:main']},
    url='https://github.com/abishara/wire-inference',
    author='Alex Bishara',
    author_email='alex.bishara@sifive.com',
    license='MIT',
    packages=['abxportinf'],
)
