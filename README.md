# ceph-perf-tool

##Preusage notes

For working only with local per-node util with json output of ceph perf counters no additional libraries required.  

For using as client-server for all ceph nodes listening required:
    * fabric

For table output required:
    * texttable

For system metrics (cpu, memory, disk usage) required:
    * psutil

Client-server works with ssh, so, you need to have password-less access for all ceph nodes from "main" node, where server is started.

Data is sent by udp on specified by used (or 9095 by default) port - take care about network access.

##Usage

###Local tool perfcollect.py

    perfcollect.py [-h] [--json] [--table] [--config CONFIG]
                          [--collection COLLECTION [COLLECTION ...]]
                          [--schemaonly] [--udp UDP UDP UDP] [--sysmetrics]

    Collect perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --json, -j            Output in json format (true by default)
      --table, -t           Output in table format (python-texttable required)
      --config CONFIG, -g CONFIG
                            Use it, if you want upload needed counter names from
                            file (json format, .counterslist as example)
      --collection COLLECTION [COLLECTION ...], -c COLLECTION [COLLECTION ...]
                            Counter collections in format collection_name counter1
                            counter2 ...
      --schemaonly, -s      Return only schema
      --udp UDP UDP UDP, -u UDP UDP UDP
                            Send result by UDP, specify host, port, packet part
                            size
      --sysmetrics, -m      Add info about cpu, memory and disk usage (psutil library required)

    Note, if you don't use both -c and -g options, all counters will be collected.


###Collecting server perfserver.py

    perfserver.py [-h] [--port PORT] [--user USER] --pathtotool PATHTOTOOL
                         [--savetofile SAVETOFILE] [--sysmetrics]

    Server for collection perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --port PORT, -p PORT  Specify port for udp connection (9095 by default)
      --user USER, -u USER  User name for all hosts (root by default)
      --pathtotool PATHTOTOOL, -t PATHTOTOOL
                            Path to remote utility perfcollect.py
      --savetofile SAVETOFILE, -s SAVETOFILE
                            Save output in file, filename required
      --sysmetrics, -m      Include info about cpu, memory and disk usage


##Example

    python perfserver.py -t ~ -p 9096 > result
