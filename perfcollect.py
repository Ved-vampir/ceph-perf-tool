#!/usr/bin/env python

""" Local utility for collecting perf counters and system info """

import sys
import json
import glob
import time
import socket
import logging
import urlparse
import argparse
import binascii
import threading
import subprocess
from os.path import splitext, basename

from daemonize import Daemonize


LOGGER_NAME = "io-perf-tool"


def parse_command_args(argv):
    """ Command line argument parsing """

    description = "Collect perf counters from ceph nodes"
    epilog = "Note, if you don't use both -c and -g options," + \
             " all counters will be collected."

    ag = argparse.ArgumentParser(description=description, epilog=epilog)
    # flags
    ag.add_argument("--json", "-j", action="store_true",
                    default=True,
                    help="Output in json format (true by default)")
    ag.add_argument("--table", "-t", action="store_true",
                    help="Output in table format (python-texttable required,"
                         " work only in local mode and not for schema)")
    ag.add_argument("--schema-only", "-s", action="store_true",
                    dest="schemaonly",
                    help="Return only schema")
    ag.add_argument("--sysmetrics", "-m", action="store_true",
                    help="Add info about cpu, memory and disk usage")
    ag.add_argument("--diff", "-d", action="store_true",
                    help="Return counters difference instead of value"
                         " (work only in timeout mode)")
    # strings
    ag.add_argument("--config", "-g", type=str,
                    metavar="FILENAME",
                    help="Use it, if you want upload needed counter names from"
                    " file (json format, .counterslist as example)")
    ag.add_argument("--collection", "-c", type=str, action="append", nargs='+',
                    metavar="COUNTER_GROUP COUNTER1 COUNTER2",
                    help="Counter collections in format "
                         "collection_name counter1 counter2 ...")
    ag.add_argument("--remote", "-u", type=str,
                    metavar="UDP://IP:PORT/SIZE",
                    help="Send result by UDP, "
                         "specify host, port, packet part size in bytes")
    ag.add_argument("--runpath", "-r", type=str,
                    default="/var/run/ceph/",
                    help="Path to ceph sockets (/var/run/ceph/ by default)")
    # int
    ag.add_argument("--timeout", "-w", type=int,
                    help="If specified, tool will work in cycle"
                    " with specified timeout in secs")

    args = ag.parse_args(argv)

    # check some errors in command line
    logger = logging.getLogger(LOGGER_NAME)
    if args.collection is not None:
        for lst in args.collection:
            if len(lst) < 2:
                logger.error("Collection argument must contain at least one counter")
                return None
    if args.config is not None and args.collection is not None:
        logger.error("You cannot add counters from config and command line together")
        return None

    return args


def define_logger():
    """ Initialization of logger"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    formatter = logging.Formatter(log_format,
                                  "%H:%M:%S")
    ch.setFormatter(formatter)
    return logger


def main():
    """ Main tool entry point """
    # init logger
    logger = define_logger()
    # get command line args
    args = parse_command_args(sys.argv[1:])
    if args is None:
        logger.error("Program terminated because of command line errors")
        exit(1)
    # prepare info for send
    sender = get_sender_object(args.remote)

    # prepare info about needed counters
    if args.config is not None:
        perf_counters = get_perfcounters_list_from_config(args.config)
    elif args.collection is not None:
        perf_counters = get_perfcounters_list_from_sysargs(args.collection)
    else:
        perf_counters = None

    sock_list = get_socket_list(args.runpath)

    if args.sysmetrics:
        import sysmets

    # if in cycle mode with udp output - start waiting for die
    if sender is not None and args.timeout is not None:
        host, port = sender.sendto
        die_event = wait_for_die(host, port+1)

    cache = None

    while True:
        # get metrics by timer
        if args.schemaonly:
            # Returns schemas of listed ceph creatures perfs
            perf_list = get_perf_data(sock_list, "schema", args.runpath)
        else:
            # Returns perf dump of listed ceph creatures
            perf_list = get_perf_data(sock_list, "dump", args.runpath)
            if perf_counters is not None:
                perf_list = select_counters(perf_counters, perf_list)

        if args.sysmetrics:
            system_metrics = sysmets.get_system_metrics(args.runpath)

        if sender is None:
            # local use
            if not args.schemaonly and args.table:
                print get_table_output(perf_list)
            else:
                if args.sysmetrics:
                    perf_list["system metrics"] = system_metrics
                if args.diff:
                    new_data = perf_list
                    perf_list = values_difference(cache, new_data)
                    cache = new_data
                print get_json_output(perf_list)

        else:
            if args.sysmetrics:
                perf_list["system metrics"] = system_metrics
            if args.diff:
                new_data = perf_list
                perf_list = values_difference(cache, new_data)
                cache = new_data
            send_by_udp(sender, get_json_output(perf_list))

        if args.timeout is None:
            break
        else:
            if sender is not None and die_event.is_set():
                break
            time.sleep(args.timeout)


def get_sender_object(url):
    """ Create connection object from input udp string """
    if url is None:
        return None
    data = urlparse.urlparse(url)
    sender = type('Sender', (), {})
    sender.sendto = (data.hostname, data.port)
    sender.size = data.path.strip("/")
    return sender


def values_difference(cache, current):
    """ Calculate difference between old values and new"""
    if cache is None:
        return {"No later values" : "first iteration"}
    diff = {}
    for block, values in cache.items():
        diff[block] = {}
        for group, counters in values.items():
            diff[block][group] = {}
            for counter, value in counters.items():
                new_data = current[block][group][counter]
                # check for complex counters
                if  not isinstance(value, dict):
                    diff[block][group][counter] = new_data - value
                else:
                    diff[block][group][counter] = {}
                    for k, v in value.items():
                        diff[block][group][counter][k] = new_data[k] - v
    return diff



def get_socket_list(path):
    """ Returns list of sockets (ceph creatures) on node"""
    sock_list = [splitext(basename(sock))[0]
                 for sock in glob.glob(path + "*.asok")]
    return sock_list


def get_perf_data(socket_list, command, path):
    """ Basic command to return schemas or dumps
        of listed ceph creatures perfs"""
    res = {}
    for sock in socket_list:
        cmd = "ceph --admin-daemon %s/%s.asok perf %s" % \
                (path, sock, command)

        PIPE = subprocess.PIPE
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                             stdout=PIPE, stderr=subprocess.STDOUT)
        res[sock] = json.loads(p.stdout.read())

    return res


def select_counters(perf_counters, perf_list):
    """ Returns selection of given counters from full list"""
    res = {}

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


def send_by_udp(conn_opts, data):
    """ Send data by udp conn_opts = [host, port, part_size]"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # prepare data
    data_len = "%i\n\r" % len(data)
    header = "begin_data_prefix%s%s\n\r" % (data_len, binascii.crc32(data))
    packet = "%s%send_data_postfix" % (header, data)

    partheader_len = len(data_len)
    part_size = int(conn_opts.size)

    b = 0
    e = part_size - partheader_len

    while b < len(packet):
        block = packet[b:b+e]
        part = data_len + block
        if sock.sendto(part, conn_opts.sendto) != len(part):
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


def wait_for_die(host, port):
    """ Create socket in separate thread for to wait die signal"""
    die_event = threading.Event()
    server = threading.Thread(target=listening_thread,
                              args=(host, port, die_event))
    server.start()
    return die_event


def listening_thread(host, port, die_event):
    """ Wait message from parent and set event to die """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    while True:
        data, (remote_ip, remote_port) = sock.recvfrom(256)
        if remote_ip == host:
            logger = logging.getLogger(LOGGER_NAME)
            logger.info("Stopped by server with message: %s", data)
            die_event.set()
            break


if __name__ == '__main__':
    pid = "/tmp/perfcollect_app%i.pid" % time.time()
    daemon = Daemonize(app="perfcollect_app", pid=pid, action=main)
    daemon.start()
