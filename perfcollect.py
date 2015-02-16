#!/usr/bin/env python

import argparse
import json
import os
import glob
import subprocess
import socket
from os.path import splitext, basename


CEPH_RUN_PATH = os.getenv("CEPH_RUN_PATH", "/var/run/ceph/")

def main():  
    # parse command line
    ag = argparse.ArgumentParser(description="Collect perf counters from ceph nodes", 
                                    epilog="Note, if you don't use both -c and -g options, all counters will be collected.")
    ag.add_argument("--json", "-j", action="store_true", default=True, help="Output in json format (true by default)")
    ag.add_argument("--table", "-t", action="store_true", help="Output in table format (python-texttable required)")
    ag.add_argument("--config", "-g", type=str, 
                        help="Use it, if you want upload needed counter names from file (json format, .counterslist as example)")
    ag.add_argument("--collection", "-c", type=str, action="append", nargs='+', 
                        help="Counter collections in format collection_name counter1 counter2 ...")
    ag.add_argument("--schemaonly", "-s", action="store_true", help="Return only schema")
    ag.add_argument("--udp", "-u", type=str, nargs=3, help="Send result by UDP, specify host, port, packet part size")
    ag.add_argument("--sysmetrics", "-m", action="store_true", help="Add info about cpu, memory and disk usage")
    args = ag.parse_args()

    # check some errors in command line
    if (args.collection is not None):
        for lst in args.collection:
            if (len(lst) < 2):
                print ("Collection argument must contain at least one counter")
                return 1
    if (args.config is not None and args.collection is not None):
        print ("You cannot add counters from config and command line together")
        return 1

    # prepare info about needed counters
    if (args.config is not None):
        perf_counters = get_perfcounters_list_from_config(args.config)
    elif (args.collection is not None):
        perf_counters = get_perfcounters_list_from_sysargs(args.collection)
    else:
        perf_counters = None

    sock_list = get_socket_list()

    if (args.schemaonly):
        # Returns schemas of listed ceph creatures perfs
        perf_list = get_perf_data(sock_list, "schema")
    else:
        # Returns perf dump of listed ceph creatures
        perf_list = get_perf_data(sock_list, "dump")
        if (perf_counters is not None):
            perf_list = select_counters(perf_counters, perf_list)

    if (args.sysmetrics):
        import sysmets
        sm = sysmets.get_system_metrics()

    if (args.udp is None):
        # local use
        if (not args.schemaonly and args.table):
            print get_table_output(perf_list)
        else:
            if (args.sysmetrics):
                perf_list["system metrics"] = sm
            print get_json_output(perf_list)

    else:
        if (args.sysmetrics):
            perf_list["system metrics"] = sm
        send_by_udp(args.udp, get_json_output(perf_list))


# Returns list of sockets (ceph creatures) on node
def get_socket_list():
    sock_list = [splitext(basename(sock))[0] for sock in glob.glob(CEPH_RUN_PATH + "*.asok")]
    return sock_list


# Basic command to return schemas or dumps of listed ceph creatures perfs
def get_perf_data(socket_list, command):
    res = dict()
    for sock in socket_list:
        cmd = "ceph --admin-daemon %s/%s.asok perf %s" % (CEPH_RUN_PATH, sock, command)
        PIPE = subprocess.PIPE
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=subprocess.STDOUT)
        res[sock] = json.loads(p.stdout.read())

    return res


# Returns selection of given counters from full list
def select_counters(perf_counters, perf_list):
    res = dict()
    # go by nodes
    for node, value in perf_list.items():
        res[node] = dict()
        # go by groups
        for group, counters in perf_counters.items():
            if group in value:
                res[node][group] = dict()
                # go by counters
                for counter in counters:
                    if counter in value[group]:
                        res[node][group][counter] = value[group][counter]

    return res


# Returns formatted output of given list of counters
# texttable module required
def get_table_output(perf_list):
    
    import texttable

    tab = texttable.Texttable()
    tab.set_deco(tab.HEADER | tab.VLINES | tab.BORDER | tab.HLINES)

    header = ['']
    header.extend(perf_list.keys())
    tab.add_row(header)
    tab.header = header

    groups = dict()
    for node, value in perf_list.items():
        for group, counters in value.items():
            if group not in groups:
                groups[group] = set()
            for counter in counters:
                groups[group].add(counter)

    for group_name, counters in groups.items():
        row = [''] * (len(perf_list.keys()) + 1)
        row[0] = group_name
        tab.add_row(row)
        for counter in counters:
                row = []
                row.append(counter)
                for key, value in perf_list.items():
                    if (group_name in value and counter in value[group_name]):
                        if type(value[group_name][counter]) != type(dict()):
                            row.append(value[group_name][counter])
                        else:
                            s = ""
                            for key1, value1 in value[group_name][counter].items():
                                s = s + key1 + " = " + str(value1) + "\n"
                            row.append(s)
                    else:
                        row.append('')
                tab.add_row(row)

    return tab.draw()



# Returns json output of given list of counters
def get_json_output(perf_list):
    return json.dumps(perf_list)


# Send data by udp conn_opts = [host, port, part_size]
def send_by_udp(conn_opts, data):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    packet = "%i\n\r%s" % (len(data), data)
    b = 0
    e = int(conn_opts[2])
    while b < len (packet):
        block = packet[b:b+e]
        if sock.sendto(block, (conn_opts[0], int(conn_opts[1]))) != len(block):
            print "Bad send"
        b += e


# function to read config file
def get_perfcounters_list_from_config(config):
    clist = open(config).read()
    return json.loads(clist)


# function to get counters list from args
def get_perfcounters_list_from_sysargs(args):
    pc = dict()
    for lst in args:
        pc[lst[0]] = []
        for i in range(1, len(lst)):
            pc[lst[0]].append(lst[i])
    return pc


if __name__ == '__main__':
    main()
