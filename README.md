# DUH inference package

The DUH inference package includes tools for inferring mappings of ports
to known bus defintions that are maintained in
[duh-bus][db].

## Install

Install using `npm` ([duh-bus][db] automatically installed):

```console
npm i sifive/duhportinf
```

*or* install using `pip`:

```console
pip install .
```

in which case [duh-bus][db] must be installed manually.
Alternatively, a `duh-bus` root directory can be specified on the command
line using `-b`.

## Run

This package includes two stand-alone command line programs for
elaborating a component of design object desribed in a [duh-document](FIXME).

### duh-portinf 

`duh-portinf` first groups ports described in a duh-document into proposed
portgroups.  These portgroups are then subsequently mapped against a bank
of [duh-bus][db] bus definitions to determine the best quality matches to these
ports.

Running `duh-portinf` will update the following entries in the
duh-document object:

* `obj["component"]["busInterfaces"]`: A list of JSON references ("$ref"),
  each of which points to a dictionary specifying the **proposed** bus
  interface for a select portgroup.  Within this list, each portgroup has
  exactly one entry.

* `obj["component"]["busInterfaceAlts"]`: A list of JSON references, each
  of which points to a dictionary specifying **alternate** bus interfaces
  for each portgroup.  

* `obj["definitions"]["busDefinitions"]`: All referenced bus interface
  dictionaries. 

* `obj["definitions"]["busMappedPortGroups"]`: A list of objects
  containing debug information for each portgroup.

##### updating the resulting `component.json`

The duh-document resulting from running `duh-portinf` can be modified to
conform with user design intent.

* Entries in the `obj["component"]["busInterface"]` list can be
  swapped with those in the `obj["component"]["busInterfacesAlts"]` for a
  particular indexed portgroup if the desired match is found listed as an
  alternate.  They can also be removed altogether if the portroup should
  not be mapped to a known bus definition.

* Referenced bus interface dictionaries can also be modified directly to
  either remove mapped ports or include new ones that were not picked up.

The modified duh-document can be validated using the
[DUH](https://github.com/sifive/duh) base suite of tools.

### duh-portbundler

`duh-portbundler` groups the ports specified in a duh-document, which are
**not** already assigned to a bus interface, into structured bundles.  

Running `duh-portbundler` will update the following entries in the
duh-document object:

* `obj["component"]["busInterfaces"]`: An updated list of JSON references
  that now includes references to structured bundles.

* `obj["definitions"]["bundleDefinitions"]`: A dictionary that includes
  the newly added structured bundles as bus interfaces in which the
  `"busType"` is specified as `"bundle"`.

[db]: https://github.com/sifive/duh-bus

<!--
## Walkthrough example

First grab the input `ark.json5` component JSON file that was generated
using [duh](https://github.com/sifive/duh).

```console
% wget whatever
```

### Infer mappings to known bus definitions

Run `duh-portinf` to infer initial bus interface matches present in the
ark design.

```console
% duh-portinf -o ark-busprop.json ark.json5
```

The resulting `ark-busprop.json` file can be modified so that the final
portgroups that are to be mapped to known bus definitions are properly
described.  JSON references for expected portgroups mapped to standard
AXI4 and AXI4-Lite sockets are included in the output
`obj["component"]["busInterfaces"]`:

```json
{TODO}
```

The portgroup with prefix `XXX_` inferred to be an XXX socket is
**not** intended to map to a standard bus definition.  This JSON reference to
`XXX_` bus interface in the `obj["component"]["busInterfaces"]` list can
simply be removed.

### Group remaining ports into bundles

Next run `duh-portbundler` to structure the remaining ports that were not
previously assigned to a bus interface into structured bundles.

```console
% duh-portbundler -o ark-final.json ark-busprop.json5
```

Ports with the shared prefix `XXX` are grouped together in a single bundle
with both a corresponding JSON reference object in
`obj["component"]["busInterfaces"]` and a definition of the bundle under
`obj["definitions"]["bundleDefinitions"]`:

```console
{TODO}
```

Additionally all ports that do not share any prefix and are not assigned
to any known bus interface are grouped together in a single bundle:

```console
{TODO}
```
-->
