#!/usr/bin/env python

""" Local utility for collecting perf counters and system info """

import os
import json
import glob
import socket
import argparse
import subprocess
from os.path import splitext, basename


# <koder>: make a cmd line option with default value
CEPH_RUN_PATH = os.getenv("CEPH_RUN_PATH", "/var/run/ceph/")


def parse_command_args():
    """ Command line argument parsing """

    description = "Collect perf counters from ceph nodes"
    epilog = "Note, if you don't use both -c and -g options," + \
             " all counters will be collected."
    ag = argparse.ArgumentParser(description=description, epilog=epilog)
    ag.add_argument("--json", "-j", action="store_true", default=True,
                    help="Output in json format (true by default)")
    ag.add_argument("--table", "-t", action="store_true",
                    help="Output in table format (python-texttable required)")
    ag.add_argument("--config", "-g", type=str,
                    help="Use it, if you want upload needed counter names from"
                    " file (json format, .counterslist as example)")
    ag.add_argument("--collection", "-c", type=str, action="append", nargs='+',
                    help="Counter collections in format "
                         "collection_name counter1 counter2 ...")
    ag.add_argument("--schemaonly", "-s", action="store_true",
                    help="Return only schema")
    ag.add_argument("--udp", "-u", type=str, nargs=3,
                    help="Send result by UDP, "
                         "specify host, port, packet part size")
    ag.add_argument("--sysmetrics", "-m", action="store_true",
                    help="Add info about cpu, memory and disk usage")
    args = ag.parse_args()

    # check some errors in command line
    if args.collection is not None:
        for lst in args.collection:
            if len(lst) < 2:
                print "Collection argument must contain at least one counter"
                return None
    if args.config is not None and args.collection is not None:
        print "You cannot add counters from config and command line together"
        return None

    return args


# <koder>: change main prototype in same way, as in perfserver
def main():
    """ Main tool entry point """
    # get command line args
    args = parse_command_args()
    if args is None:
        print "Program terminated because of command line errors"
        exit(1)

    # prepare info about needed counters
    if args.config is not None:
        perf_counters = get_perfcounters_list_from_config(args.config)
    elif args.collection is not None:
        perf_counters = get_perfcounters_list_from_sysargs(args.collection)
    else:
        perf_counters = None

    sock_list = get_socket_list()

    if args.schemaonly:
        # Returns schemas of listed ceph creatures perfs
        perf_list = get_perf_data(sock_list, "schema")
    else:
        # Returns perf dump of listed ceph creatures
        perf_list = get_perf_data(sock_list, "dump")
        if perf_counters is not None:
            perf_list = select_counters(perf_counters, perf_list)

    if args.sysmetrics:
        import sysmets
        system_metrics = sysmets.get_system_metrics()

    if args.udp is None:
        # local use
        if not args.schemaonly and args.table:
            print get_table_output(perf_list)
        else:
            if args.sysmetrics:
                perf_list["system metrics"] = system_metrics
            print get_json_output(perf_list)

    else:
        if args.sysmetrics:
            perf_list["system metrics"] = system_metrics
        # <koder>: we need to think about compact binary serialization
        send_by_udp(args.udp, get_json_output(perf_list))


def get_socket_list():
    """ Returns list of sockets (ceph creatures) on node"""
    sock_list = [splitext(basename(sock))[0]
                 for sock in glob.glob(CEPH_RUN_PATH + "*.asok")]
    return sock_list


def get_perf_data(socket_list, command):
    """ Basic command to return schemas or dumps
        of listed ceph creatures perfs"""
    res = {}
    for sock in socket_list:
        cmd = "ceph --admin-daemon %s/%s.asok perf %s" % \
                (CEPH_RUN_PATH, sock, command)

        # <koder>: use subprocess.check_output() instead
        PIPE = subprocess.PIPE
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                             stdout=PIPE, stderr=subprocess.STDOUT)
        res[sock] = json.loads(p.stdout.read())

    return res


def select_counters(perf_counters, perf_list):
    """ Returns selection of given counters from full list"""
    res = {}
    # <koder>: does this code just copy a two dicts?
    # go by nodes
    for node, value in perf_list.items():
        res[node] = {}
        # go by groups
        for group, counters in perf_counters.items():
            if group in value:
                res[node][group] = {}
                # go by counters
                for counter in counters:
                    if counter in value[group]:
                        res[node][group][counter] = value[group][counter]

    return res


def get_table_output(perf_list):
    """ Returns formatted output of given list of counters
       texttable module required """
    import texttable

    tab = texttable.Texttable()
    tab.set_deco(tab.HEADER | tab.VLINES | tab.BORDER | tab.HLINES)

    header = ['']
    header.extend(perf_list.keys())
    tab.add_row(header)
    tab.header = header

    line_len = len(header)

    # select group and counter names
    groups = {}
    for node, value in perf_list.items():
        for group, counters in value.items():
            groups.setdefault(group, set()).update(counters)

    for group_name, counters in groups.items():
        row = [''] * line_len
        row[0] = group_name
        tab.add_row(row)

        for counter in counters:
            row = []
            row.append(counter)
            for key, value in perf_list.items():
                if group_name in value and counter in value[group_name]:

                    perf_val = value[group_name][counter]
                    # next if is needed because of result of perf command
                    # json contains either numbers or sets of values
                    # in this section, so dict can be here
                    if not isinstance(perf_val, dict):
                        row.append(perf_val)
                    else:
                        s = ""
                        for key1, value1 in perf_val.items():
                            s += "{0}={1}\n".format(key1, str(value1))
                        row.append(s)
                else:
                    row.append('')
            tab.add_row(row)

    return tab.draw()


def get_json_output(perf_list):
    """ Returns json output of given list of counters"""
    return json.dumps(perf_list)


# <koder>: attach crc32 to data. It's available in zipfile module
def send_by_udp(conn_opts, data):
    """ Send data by udp conn_opts = [host, port, part_size]"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # <koder>: this code is sencible to size field corruption
    # <koder>: which may cause a lot of problems
    # <koder>: pass size field three times and select only if two is same
    #
    # <koder>: also add prefix and postfix to reliably define begin and end
    # <koder>: of data. This allow you to easily recover from
    # <koder>: broken pransmit

    packet = "%i\n\r%s" % (len(data), data)
    b = 0
    e = int(conn_opts[2])
    addr = (conn_opts[0], int(conn_opts[1]))

    while b < len(packet):
        block = packet[b:b+e]
        if sock.sendto(block, addr) != len(block):
            print "Bad send"
            break
        b += e


def get_perfcounters_list_from_config(config):
    """ function to read config file"""
    clist = open(config).read()
    return json.loads(clist)


def get_perfcounters_list_from_sysargs(args):
    """ function to get counters list from args"""
    pc = dict()
    for lst in args:
        pc[lst[0]] = []
        for i in range(1, len(lst)):
            pc[lst[0]].append(lst[i])
    return pc


if __name__ == '__main__':
    main()
