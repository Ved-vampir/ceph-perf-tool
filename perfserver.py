#!/usr/bin/env python
""" Server for collecting performance data from all ceph nodes"""

import os
import sys
import time
import Queue
import socket
import logging
import argparse
import threading

import sender
from execute import execute, ExecuteError
from logger import define_logger
from ceph import get_osds_list, get_mons_or_mds_ips, get_osds_ips


LOGGER_NAME = "io-perf-tool"


def listen_thread(udp_sender, result, term_event):
    """ Main listenig thread for socket
        Listen port, while waiting con_count answers
        Write answers to stdout or to file, if it specified """


    while True:

        try:
            # return not None, if packet is ready
            ready = udp_sender.recv_by_protocol()

            if ready is not None:
                result.put(ready)

        except sender.Timeout:
            # no answer yet - check, if server want to kill us
            if term_event.is_set():
                break
        else:
            if term_event.is_set():
                break


def parse_command_args(argv):
    """ Command line argument parsing """
    arg = argparse.ArgumentParser(description="Server for collecting"
                                              " perf counters from ceph nodes")
    # block with default values
    arg.add_argument("--port", "-p", type=int,
                     default=9095,
                     help="Specify port for udp connection (9095 by default)")
    arg.add_argument("--user", "-u", type=str,
                     default="root",
                     help="User name for all hosts (root by default)")
    arg.add_argument("--timeout", "-w", type=int,
                     default=5,
                     help="Time between collecting (5 by default)")
    arg.add_argument("--partsize", "-b", type=int,
                     default=4096,
                     help="Part size for udp packet (4096 by default)")
    # required params
    arg.add_argument("--path-to-tool", "-t", type=str, required=True,
                     metavar="PATH_TO_TOOL", dest="pathtotool",
                     help="Path to remote utility perfcollect.py")
    # params with value
    arg.add_argument("--save-to-file", "-s", type=str,
                     metavar="FILENAME", dest="savetofile",
                     help="Save output in file, filename required")
    arg.add_argument("--localip", "-i", type=str,
                     metavar="IP",
                     help="Local ip for udp answer (if you don't specify it,"
                          " not good net might be used)")
    # flag params
    arg.add_argument("--sysmetrics", "-m", action="store_true",
                     help="Include info about cpu, memory and disk usage")
    arg.add_argument("--diff", "-d", action="store_true",
                     help="Get not counters values, but their difference "
                          "time by time")
    arg.add_argument("--copytool", "-y", action="store_true",
                     help="Copy tool to all nodes to path from -t")
    arg.add_argument("--totaltime", "-a", type=int,
                     help="Total time in secs to collect (if None - server "
                          "never stop itself)")
    arg.add_argument("--extradata", "-e", action="store_true",
                    help="To collect common data about cluster "
                         " (logs, confs, etc)")

    return arg.parse_args(argv)


def real_main(args, term_event):
    """Server starts from here"""
    logger = logging.getLogger(LOGGER_NAME)
    # find nodes
    osd_list = get_osds_list()
    osd_ip_list = get_osds_ips(osd_list)
    mon_ip_list = get_mons_or_mds_ips("mon")
    mds_ip_list = get_mons_or_mds_ips("mds")
    ip_list = osd_ip_list | mon_ip_list | mds_ip_list

    # locate myself
    if args.localip is None:
        args.localip = socket.gethostbyname_ex(socket.gethostname())[2][0]

    localy = False
    if args.localip in ip_list:
        ip_list.remove(args.localip)
        localy = True

    # test connection
    test_ips(ip_list)

    # copy tool, if user want
    if args.copytool:
        copy_tool(ip_list, args.pathtotool, args.user, localy)

    # start socket listening
    udp_sender = sender.Sender(port=int(args.port), size=int(args.partsize))
    result = Queue.Queue()
    server = threading.Thread(target=listen_thread,
                              args=(udp_sender,
                                    result, term_event))
    server.start()
    start_time = time.time()
    if args.totaltime is not None:
        logger.info("Tests will be finished in a %d sec", args.totaltime)

    # begin to collect counters

    # supress connection to localhost
    cmd = prepare_tool_cmd(args)
    if localy:
        start_tool_localy(cmd)

    get_perfs_from_all_nodes(args.user, cmd, ip_list)

    logger.info("Collect daemons started, now waiting for answer...")

    while not term_event.is_set():
        # stop if timeout is setted
        if args.totaltime is not None:
            time_now = time.time() - start_time
            if time_now > args.totaltime:
                # term_event for other threads
                term_event.set()
                logger.info("Test time is over")
                break
            # wait not more than remaining
            really_big_timeout = args.totaltime - time_now
        else:
            # without any timeout KeyboardInterrupt will not raise
            really_big_timeout = sys.maxint
        try:
            data = result.get(timeout=really_big_timeout)
            # proceed returned data
            if args.savetofile is None:
                logger.info(data)
            else:
                with open(args.savetofile, 'a') as f:
                    f.write("\n---\n")
                    f.write(data)
        except Queue.Empty:
            # no matter - timeout finish before info come
            continue

    # wait for server termination
    server.join()
    # kill remote tool (if it is not killed yet)
    send_die_to_tools(ip_list, udp_sender, localy, args.localip)
    if args.extradata:
        collect_extra_results(ip_list, args.user, localy)


def main(argv):
    """ Shell for main because of ctrl-c exit """
    # start logging
    logger = define_logger(LOGGER_NAME)
    # parse command line
    args = parse_command_args(argv[1:])
    # create termination event
    term_event = threading.Event()
    # start main thread
    main_thread = threading.Thread(target=real_main,
                                   args=(args, term_event))
    main_thread.start()
    logger.info("Main thread is started... Use Ctrl+C for exit.")

    try:
        # this part only waits for ctrl+c
        # or for timeout termination from main thread
        while not term_event.is_set():
            pass

    except KeyboardInterrupt:
        logger.info("Finalization...")
        # kill our threads
        term_event.set()
        # wait for server termination
        main_thread.join()


def send_die_to_tools(ip_list, udp_sender, localy=False, localip=""):
    """ Send message to die to tools"""
    logger = logging.getLogger(LOGGER_NAME)
    for ip in ip_list:
        if not udp_sender.verified_send(ip, "Time to die"):
            logger.error("Unsuccessfull die signal to %s", ip)
        else:
            logger.info("Successfully killed %s", ip)
    if localy:
        if not udp_sender.verified_send(localip, "Time to die"):
            logger.error("Unsuccessfull die signal to  %s", localip)


def test_ips(ip_list):
    """ Ping all ips to understand that they are reachable """
    logger = logging.getLogger(LOGGER_NAME)
    ips = set(ip_list)
    cmd = "ping  -c 1 -w 2 {0} > /dev/null 2>&1"
    for ip in ips:
        try:
            execute(cmd.format(ip))
        except ExecuteError:
            ip_list.remove(ip)
            logger.warning("Ip %s is unreachable, exclude it", ip)
    ip_list = ips


def copy_tool(ip_list, path, user, localy=False):
    """ Copy tool and libs to specified ips on path"""
    logger = logging.getLogger(LOGGER_NAME)
    tool_names = ["perfcollect.py", "sysmets.py", "ceph_srv_info.py",
                  "sender.py", "packet.py", "logger.py", "ceph.py",
                  "daemonize.py", "umsgpack.py", "sh.py", "execute.py"]
    bad_ips = []
    for ip in ip_list:
        try:
            for tool in tool_names:
                full_path = os.path.join(path, tool)
                cmd = "scp %s %s@%s:%s" % (tool, user, ip, full_path)
                execute(cmd)
        except ExecuteError:
            logger.warning("Cannot do copy on ip %s, exclude it.", ip)
            bad_ips.append(ip)

    if len(bad_ips) > 0:
        ip_list = [ip for ip in ip_list if ip not in bad_ips]

    if localy:
        for tool in tool_names:
            full_path = os.path.join(path, tool)
            cmd = "cp {0} {1}".format(tool, full_path)
            execute(cmd)


def collect_extra_results(ip_list, user, localy=False):
    """ Get extra results archives from all nodes """
    logger = logging.getLogger(LOGGER_NAME)
    resname = "results_{0}".format(time.time())
    os.mkdir(resname)
    arch_path = "/tmp/extra_data.tar.gz"
    copy_name = resname + "/{0}.tar.gz"
    for ip in ip_list:
        try:
            real_name = copy_name.format(ip)
            cmd = "scp %s@%s:%s %s" % (user, ip, arch_path, real_name)
            execute(cmd)
        except ExecuteError:
            logger.warning("Cannot copy results from ip %s, skip it.", ip)

    if localy:
        real_name = copy_name.format("localhost")
        cmd = "cp {0} {1}".format(arch_path, real_name)
        execute(cmd)

    logger.info("Extra data is stored in results folder %s", resname)


def prepare_tool_cmd(args):
    """ Return params for tool start"""
    path = args.pathtotool
    port = args.port
    local_ip = args.localip
    part_size = args.partsize
    timeout = args.timeout
    sysmets = args.sysmetrics
    get_diff = args.diff
    extra_data = args.extradata

    # prepare args
    params = "-u UDP://%s:%s/%s -w %i" % (local_ip, port, part_size, timeout)
    if sysmets:
        params += " -m"
    if get_diff:
        params += " -d"
    if extra_data:
        params += " -e"

    cmd = "python %s/perfcollect.py %s" % (path, params)

    return cmd


def start_tool_localy(cmd):
    """ Start tool localy on current node """
    execute(cmd)


def get_perfs_from_all_nodes(user, cmd, ip_list):
    """ Start tool from path on every ip in ip_list
        Access by user, answer on port
        Return system metrics also, if sysmets=True """

    for ip in ip_list:
        ssh = "ssh {0}@{1} {2}".format(user, ip, cmd)
        execute(ssh)

if __name__ == '__main__':
    exit(main(sys.argv))
