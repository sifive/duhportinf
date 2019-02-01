## Install

Install using pip.

```
pip install .
```

## Run

```console
# abxportinf -h
usage: abxportinf [-h] -b DUH_BUS [-o OUTPUT] component_json5

positional arguments:
  component_json5       input component.json5 with port list of top-level
                        module

optional arguments:
  -h, --help            show this help message and exit
  -b DUH_BUS, --duh-bus DUH_BUS
                        duh-bus root direcotry that contains bus
                        specifications
  -o OUTPUT, --output OUTPUT
                        output path to busprop.json with proposed bus mappings
                        for select groups of ports
```

To recognize known bus and memory interfaces, specify a
[duh-bus](https://github.com/sifive/duh-bus) root together with an input
`component.json5` file that contains the all the ports extracted from a
component top-level module using [duh](https://github.com/sifive/duh).

