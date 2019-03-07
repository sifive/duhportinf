from setuptools import setup

setup(
    name='duhportinf',
    version='0.1.0',
    description='library to match flat named port list to library of bus specifications',
    entry_points = {'console_scripts': [
        'duh-portinf=duhportinf.main_portinf:main',
        'duh-portbundler=duhportinf.main_portbundler:main',
    ]},
    url='https://github.com/sifive/duhportinf',
    author='Alex Bishara',
    author_email='alex.bishara@sifive.com',
    license='MIT',
    packages=['duhportinf'],
)
