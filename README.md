# ceph-perf-tool

##Preusage notes

For working only with local per-node util with json output of ceph perf counters no additional libraries required.  

For system metrics (cpu, memory, disk usage) required:

    * psutil

For using as client-server for all ceph nodes listening required:

    * sh
    * fabric
    * psutil

For table output required:

    * texttable

Client-server works with ssh, so, you need to have password-less access for all ceph nodes from "main" node, where server is started.

Data is sent by udp on specified by used (or 9095 by default) port - take care about network access.

##Usage

###Local tool perfcollect.py

This tool can be used localy for collection performance info from local ceph instances. Also it is used as client, which can send this info by udp to server - by this way we can collect data from all nodes.

Tool has two modes: one call - one output and one call - multiply output (collecting of performance info by timer)

    perfcollect.py [-h] [--json] [--table] [--schema-only] [--sysmetrics]
                      [--diff] [--config FILENAME]
                      [--collection COUNTER_GROUP COUNTER1 COUNTER2 [COUNTER_GROUP COUNTER1 COUNTER2 ...]]
                      [--remote UDP://IP:PORT/SIZE] [--runpath RUNPATH]
                      [--timeout TIMEOUT]

    Collect perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --json, -j            Output in json format (true by default)
      --table, -t           Output in table format (python-texttable required,
                            work only in local mode and not for schema)
      --schema-only, -s     Return only schema
      --sysmetrics, -m      Add info about cpu, memory and disk usage
      --diff, -d            Return counters difference instead of value (work only
                            in timeout mode)
      --config FILENAME, -g FILENAME
                            Use it, if you want upload needed counter names from
                            file (json format, .counterslist as example)
      --collection COUNTER_GROUP COUNTER1 COUNTER2 [COUNTER_GROUP COUNTER1 COUNTER2 ...], -c COUNTER_GROUP COUNTER1 COUNTER2 [COUNTER_GROUP COUNTER1 COUNTER2 ...]
                            Counter collections in format collection_name counter1
                            counter2 ...
      --remote UDP://IP:PORT/SIZE, -u UDP://IP:PORT/SIZE
                            Send result by UDP, specify host, port, packet part
                            size in bytes
      --runpath RUNPATH, -r RUNPATH
                            Path to ceph sockets (/var/run/ceph/ by default)
      --timeout TIMEOUT, -w TIMEOUT
                            If specified, tool will work in cycle with specified
                            timeout in secs

    Note, if you don't use both -c and -g options, all counters will be collected.


###Collecting server perfserver.py

Server for working with all nodes. Server must be started from ceph node, because it find other nodes asking ceph about them.

Server starts perfcollect tool on each ceph node and communicate with it. So, you need have this tool and it's libs (if you want get system metrics) on each node on given in -t argument path. If you don't want copy it by yourself, use -y argument (scp command runs).

Server must have password-less ssh access for other nodes. Specify user, if you have no access to root.

Exit from server now is possible only via Ctrl+C (KeyboardInterrupt)

    perfserver.py [-h] [--port PORT] [--user USER] [--timeout TIMEOUT]
                     [--partsize PARTSIZE] [--ceph CEPH] --path-to-tool
                     PATH_TO_TOOL [--save-to-file FILENAME] [--localip IP]
                     [--sysmetrics] [--diff] [--copytool]

    Server for collecting perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --port PORT, -p PORT  Specify port for udp connection (9095 by default)
      --user USER, -u USER  User name for all hosts (root by default)
      --timeout TIMEOUT, -w TIMEOUT
                            Time between collecting (5 by default)
      --partsize PARTSIZE, -b PARTSIZE
                            Part size for udp packet (4096 by default)
      --ceph CEPH, -c CEPH  Ceph command line command (ceph by default)
      --path-to-tool PATH_TO_TOOL, -t PATH_TO_TOOL
                            Path to remote utility perfcollect.py
      --save-to-file FILENAME, -s FILENAME
                            Save output in file, filename required
      --localip IP, -i IP   Local ip for udp answer (if you don't specify it, not
                            good net might be used)
      --sysmetrics, -m      Include info about cpu, memory and disk usage
      --diff, -d            Get not counters values, but their difference time by
                            time
      --copytool, -y        Copy tool to all nodes to path from -t



##Example

Start server on 9096 port with coping of tool to home root directory, get counters difference and others values by default

    python perfserver.py -t ~ -p 9096 -y -d

Start server on default port with system metrics getting and file output, get result every 30 sec

    python perfserver.py -t ~ -w 30 -s test.out -m

