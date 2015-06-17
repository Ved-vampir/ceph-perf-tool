#!/usr/bin/env python

""" Local utility for collecting perf counters and system info """

import os
import sys
import path
import json
import time
import logging
import argparse
import threading

from daemonize import Daemonize

import ceph
import sender
# import sysmets
from logger import define_logger


LOGGER_NAME = "perfcollect_app"

extra_data_commands = [
    ("config", "show"),
    ("mon_status"),
    ("status"),
    ("dump_op_pq_state"),
    ("dump_watchers"),
    ("dump_blacklist"),
    ("dump_ops_in_flight"),
    ("dump_historic_ops")]


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
    ag.add_argument("--extradata", "-e", action="store_true",
                    help="To collect common data about cluster "
                         " (logs, confs, etc)")
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


def main():
    """ Main tool entry point """
    # init logger
    logger = define_logger(LOGGER_NAME)
    # get command line args
    args = parse_command_args(sys.argv[1:])
    if args is None:
        logger.error("Program terminated because of command line errors")
        exit(1)

    if args.sysmetrics:
        import sysmets

    # prepare folder for extradata
    if args.extradata:
        dirname = "perfcollect{0}".format(time.time())
        os.mkdir(dirname)


    # prepare info for send
    if args.remote is not None:
        udp_sender = sender.Sender(url=args.remote)

    # prepare info about needed counters
    if args.config is not None:
        perf_counters = get_perfcounters_list_from_config(args.config)
    elif args.collection is not None:
        perf_counters = get_perfcounters_list_from_sysargs(args.collection)
    else:
        perf_counters = None

    # get local ceph socket list
    sock_list = ceph.get_socket_list(args.runpath)

    # if in cycle mode with udp output - start waiting for die
    if args.remote is not None and args.timeout is not None:
        die_event, stop_event = wait_for_die(udp_sender)

    cache = None

    try:

        while True:
            # get metrics by timer
            if args.schemaonly:
                # Returns schemas of listed ceph creatures perfs
                perf_list = ceph.get_perf_data(sock_list, ("perf", "schema"), args.runpath)
            else:
                # Returns perf dump of listed ceph creatures
                perf_list = ceph.get_perf_data(sock_list, ("perf", "dump"), args.runpath)
                if perf_counters is not None:
                    perf_list = select_counters(perf_counters, perf_list)

            if args.sysmetrics:
                system_metrics = sysmets.get_system_metrics(args.runpath)

            if args.remote is None:
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
                    if cache is not None:
                        new_data = perf_list
                        perf_list = values_difference(cache, new_data)
                        cache = new_data
                        send_by_udp(udp_sender, perf_list)
                    else:
                        cache = perf_list
                else:
                    send_by_udp(udp_sender, perf_list)

            if args.timeout is None:
                break
            else:
                if args.remote is not None and die_event.is_set():
                    break
                time.sleep(args.timeout)
    except Exception as e:
        # if anything wrong - need to kill thread
        if stop_event is not None:
            stop_event.set()
        raise e


def save_extra_data(socket_list, run_path, dirname):
    """ Get and save extradata to files"""
    cur_time = time.time()
    frmt = "{0} : {1} :\n{2}"
    for command in extra_data_commands:
        data_list = ceph.get_perf_data(socket_list, command, run_path)
        for sock in socket_list:
            with open(path.join(dirname, sock), "a") as f:
                fmt_data = frmt.format(cur_time, command, data_list[sock])
                f.write(fmt_data)


def save_logs()


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
    for value in perf_list.values():
        for group, counters in value.items():
            groups.setdefault(group, set()).update(counters)

    for group_name, counters in groups.items():
        row = [''] * line_len
        row[0] = group_name
        tab.add_row(row)

        for counter in counters:
            row = []
            row.append(counter)
            for value in perf_list.values():
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


def send_by_udp(udp_sender, data):
    """ Send data by udp"""
    udp_sender.send_by_protocol(data)


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


def wait_for_die(udp_sender):
    """ Create socket in separate thread for to wait die signal"""
    die_event = threading.Event()
    stop_event = threading.Event()
    server = threading.Thread(target=listening_thread,
                              args=(udp_sender, die_event, stop_event))
    server.start()
    return die_event, stop_event


def listening_thread(die_sender, die_event, stop_event):
    """ Wait message from parent and set event to die """
    # use port+1 because of conflict with server in case of local use
    #die_sender = sender.Sender(port=port, host=host)

    command = die_sender.recv_with_answer(stop_event)
    # check, that it is not interruption
    if command is not None:
        data, remote_ip = command
        if remote_ip == die_sender.sendto[0]:
            logger = logging.getLogger(LOGGER_NAME)
            logger.info("Stopped by server with message: %s", data)
            die_event.set()


if __name__ == '__main__':
    pid = "/tmp/perfcollect_app%i.pid" % time.time()
    daemon = Daemonize(app="perfcollect_app", pid=pid, action=main)
    daemon.start()
