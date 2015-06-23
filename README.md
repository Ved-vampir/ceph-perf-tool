# ceph-perf-tool

##Preusage notes

For main program capabilities no additional libraries required.  

For system metrics (cpu, memory, disk usage) required:

    * psutil

For table output required:

    * texttable

Client-server works with ssh, so, you need to have password-less access for all ceph nodes from "main" node, where server is started.
For Fuel env controller node will be the good choice.
Ceph must be installed on node, from which you start server.

Data is sent by udp on specified by used (or 9095 by default) port - take care about network access.

##Usage

###Local tool perfcollect.py

This tool can be used localy for collection performance info from local ceph instances. Also it is used as client, which can send this info by udp to server - by this way we can collect data from all nodes.

Tool has two modes: one call - one output and one call - multiply output (collecting of performance info by timer)

    perfserver.py [-h] [--port PORT] [--user USER] [--timeout TIMEOUT]
                         [--partsize PARTSIZE] --path-to-tool PATH_TO_TOOL
                         [--save-to-file FILENAME] [--localip IP] [--sysmetrics]
                         [--diff] [--copytool] [--totaltime TOTALTIME]
                         [--extradata]

    Server for collecting perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --port PORT, -p PORT  Specify port for udp connection (9095 by default)
      --user USER, -u USER  User name for all hosts (root by default)
      --timeout TIMEOUT, -w TIMEOUT
                            Time between collecting (5 by default)
      --partsize PARTSIZE, -b PARTSIZE
                            Part size for udp packet (4096 by default)
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
      --totaltime TOTALTIME, -a TOTALTIME
                            Total time in secs to collect (if None - server never
                            stop itself)
      --extradata, -e       To collect common data about cluster (logs, confs,
                            etc)

    Note, if you don't use both -c and -g options, all counters will be collected.


###Collecting server perfserver.py

Server for working with all nodes. Server must be started from ceph node, because it find other nodes asking ceph about them.

Server starts perfcollect tool on each ceph node and communicate with it. So, you need have this tool and it's libs (if you want get system metrics) on each node on given in -t argument path. If you don't want copy it by yourself, use -y argument (scp command runs).

Server must have password-less ssh access for other nodes. Specify user, if you have no access to root.

Exit from server now is possible only via Ctrl+C (KeyboardInterrupt)

        perfserver.py [-h] [--port PORT] [--user USER] [--timeout TIMEOUT]
                         [--partsize PARTSIZE] --path-to-tool PATH_TO_TOOL
                         [--save-to-file FILENAME] [--localip IP] [--sysmetrics]
                         [--diff] [--copytool] [--totaltime TOTALTIME]
                         [--extradata]

    Server for collecting perf counters from ceph nodes

    optional arguments:
      -h, --help            show this help message and exit
      --port PORT, -p PORT  Specify port for udp connection (9095 by default)
      --user USER, -u USER  User name for all hosts (root by default)
      --timeout TIMEOUT, -w TIMEOUT
                            Time between collecting (5 by default)
      --partsize PARTSIZE, -b PARTSIZE
                            Part size for udp packet (4096 by default)
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
      --totaltime TOTALTIME, -a TOTALTIME
                            Total time in secs to collect (if None - server never
                            stop itself)
      --extradata, -e       To collect common data about cluster (logs, confs,
                            etc)




##Example

The full-function call
    python perfserver.py -y -i 192.168.0.4 -p 9989 -t ~ -s test.log -a 10 -e

    It will copy tool to home directory of alll nodes, bind to ip 192.168.0.4:9989, will collect data during 10 sec to test.log file and also get additional information from all nodes (it will be stored in archive in local directory on server).

If you have used flag '-y' once, you can don't use it later, if you are sure, that perfcollect tool was not deleted on all nodes. This can be used to prevent new copying and save some time. If you don't want to take care about it, use '-y' flag always.

Start server on 9096 port with coping of tool to home root directory, get counters difference and others values by default

    python perfserver.py -t ~ -p 9096 -y -d

Start server on default port with system metrics getting and file output, get result every 30 sec

    python perfserver.py -t ~ -w 30 -s test.out -m

Example with output:
    python perfserver.py -y -i 192.168.0.4 -p 9989 -t ~ -s test.log -a 10 -e
    16:08:20 - INFO - io-perf-tool - Main thread is started... Use Ctrl+C for exit.
    16:08:30 - INFO - io-perf-tool - Tests will be finished in a 10 sec
    16:08:32 - INFO - io-perf-tool - Collect daemons started, now waiting for answer...
    16:08:40 - INFO - io-perf-tool - Test time is over
    16:08:40 - INFO - io-perf-tool - Successfully killed 192.168.0.11
    16:08:40 - INFO - io-perf-tool - Successfully killed 192.168.0.5
    16:08:40 - INFO - io-perf-tool - Extra data is stored in results folder
