## Install

Install using pip:

```console
pip install .
```

*or* npm:

```console
npm i sifive/duhportinf
```

[duh-bus](https://github.com/sifive/duh-bus) must also be installed in
order to recognize known bus and memory interfaces.  Alternatively, a
`duh-bus` root directory can be specified on the command line using `-b`.

## Run

The `duhportinf` package includes two stand-alone command line programs:
`duh-portinf` for inferring mappings of groups of ports to a known bus
defintions, and `duh-portbundler` for organizing the remaining ports not
mapped to a bus definition into structured bundles.  

Both `duhportinf` programs require a `component.json5` file as input,
which can be generated using [duh](https://github.com/sifive/duh).

### duh-portinf 

`duh-portinf` first groups the flat list of ports specified in the input
`component.json5` file object (under `obj["component"]["model"]["ports"]`)
into proposed portgroups.  These portgroups are then subsequently mapped
against a bank of known bus definitions to determine the best quality
matches to these ports.

Running `duh-portinf` will create the following new entries in the object
specified in the output `component.json` file:

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
  containing debug information for each portgroup that includes

  - `"num_ports"`: number of ports within this interface.  Note, ports
    inferred as belonging to an indexed vector are counted only once.

  - `"prefix"`: common prefix of the names of all ports within this
    portgroup.

  - `"cost-dir-mismatch"`: Number of ports within the portgroup that did
    not match the direction of the mapped logical port specified in the
    **proposed** bus interface.  

  - `"cost-width-mismatch"`: Number of ports within the portgroup that did
    not match the width of the mapped logical port specified in the
    **proposed** bus interface.  If the width for a port was either not
    specified in the duh-bus defintion or parameterized in the component
    and could not be properly inferred by `duh`, then it will be counted
    as a width mismatch.


##### updating the resulting `component.json`

After running `duh-portinf`, the resulting `component.json` file can be
modified to conform with the design intent of the component.

Entries in the `obj["component"]["busInterfaceAlts"]` list can be swapped
with those in the `obj["component"]["busInterfaces"]` for a particular
indexed portgroup if the desired match is found listed as an alternate.
However, a portgroup can only have a **single** bus interface specified in
`obj["component"]["busInterfaces"]`.  The referenced bus interface
dictionaries can also be modified directly to either remove mapped ports or
include new ones that were not picked up.

Entries within the `obj["component"]["busInterfaces"]` that correspond to
portgroups that should not be mapped to known bus definitions can simply
be removed from this list. 

### duh-portbundler

`duh-portbundler` groups the ports specified in the input
`component.json5` file object, which are **not** already assigned to a bus
interface, into structured bundles.  If run on the `component.json` file
resulting from `duh-portinf`, it will group the remaining ports not mapped
to a bus definition into structured bundles.

Running `duh-portbundler` will update the entries in the object specified
in the output `component.json` file:

* `obj["component"]["busInterfaces"]`: An updated list of JSON references
  that now includes references to structured bundles.

* `obj["definitions"]["bundleDefinitions"]`: A dictionary that includes
  the newly added structured bundles as bus interfaces in which the
  `"busType"` is specified as `"bundle"`.

