# ceph-perf-tool

##Preusage notes

For working only with local per-node util with json output of ceph perf counters no additional libraries required.  

For system metrics (cpu, memory, disk usage) required:

    * psutil

For using as client-server for all ceph nodes listening required:

    * fabric
    * psutil

For table output required:

    * texttable

Client-server works with ssh, so, you need to have password-less access for all ceph nodes from "main" node, where server is started.

Data is sent by udp on specified by used (or 9095 by default) port - take care about network access.

##Usage

###Local tool perfcollect.py

    perfcollect.py [-h] [--json] [--table] [--schemaonly] [--sysmetrics]
                      [--config CONFIG]
                      [--collection COLLECTION [COLLECTION ...]]
                      [--udp UDP UDP UDP] [--runpath RUNPATH]
                      [--timeout TIMEOUT]

    Collect perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --json, -j            Output in json format (true by default)
      --table, -t           Output in table format (python-texttable required)
      --schemaonly, -s      Return only schema
      --sysmetrics, -m      Add info about cpu, memory and disk usage
      --config CONFIG, -g CONFIG
                            Use it, if you want upload needed counter names from
                            file (json format, .counterslist as example)
      --collection COLLECTION [COLLECTION ...], -c COLLECTION [COLLECTION ...]
                            Counter collections in format collection_name counter1
                            counter2 ...
      --udp UDP UDP UDP, -u UDP UDP UDP
                            Send result by UDP, specify host, port, packet part
                            size
      --runpath RUNPATH, -r RUNPATH
                            Path to ceph sockets (/var/run/ceph/ by default)
      --timeout TIMEOUT, -w TIMEOUT
                            If specified, tool will work in cycle with specified
                            timeout in secs

    Note, if you don't use both -c and -g options, all counters will be collected.


###Collecting server perfserver.py

    perfserver.py [-h] [--port PORT] [--user USER] [--timeout TIMEOUT]
                     [--partsize PARTSIZE] [--ceph CEPH] --pathtotool
                     PATHTOTOOL [--savetofile SAVETOFILE] [--localip LOCALIP]
                     [--sysmetrics] [--copytool]

    Server for collecting perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --port PORT, -p PORT  Specify port for udp connection (9095 by default)
      --user USER, -u USER  User name for all hosts (root by default)
      --timeout TIMEOUT, -w TIMEOUT
                            Max time in sec waiting for answers (30 by default)
      --partsize PARTSIZE, -b PARTSIZE
                            Part size for udp packet (4096 by default)
      --ceph CEPH, -c CEPH  Ceph command line command (ceph by default)
      --pathtotool PATHTOTOOL, -t PATHTOTOOL
                            Path to remote utility perfcollect.py
      --savetofile SAVETOFILE, -s SAVETOFILE
                            Save output in file, filename required
      --localip LOCALIP, -i LOCALIP
                            Local ip for udp answer (if you don't specify it, not
                            good net might be used)
      --sysmetrics, -m      Include info about cpu, memory and disk usage
      --copytool, -y        Copy tool to all nodes to path from -t



##Example

    python perfserver.py -t ~ -p 9096 -y
