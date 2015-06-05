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


# import psutil
# from fabric import tasks
# from fabric.api import env, run, hide, task, parallel
# from fabric.network import disconnect_all

import sender
from sender import execute
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

    return arg.parse_args(argv)


def main(argv):
    """ Server starts from here """
    # start logging
    logger = define_logger(LOGGER_NAME)
    # parse command line
    args = parse_command_args(argv[1:])

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

    # copy tool, if user want
    if args.copytool:
        copy_tool(ip_list, args.pathtotool, args.user, localy)

    # start socket listening
    udp_sender = sender.Sender(port=int(args.port), size=int(args.partsize))
    result = Queue.Queue()
    term_event = threading.Event()
    server = threading.Thread(target=listen_thread,
                              args=(udp_sender,
                                    result, term_event))
    try:
        server.start()
        start_time = time.time()

        # begin to collect counters

        logger.info("Now waiting for answer... Use Ctrl+C for exit.")

        # supress connection to localhost
        cmd = prepare_tool_cmd(args)
        if localy:
            start_tool_localy(cmd)

        # tools = threading.Thread(target=get_perfs_from_all_nodes,
        #                          args=(args.user, cmd, ip_list))
        # tools.start()
        get_perfs_from_all_nodes(args.user, cmd, ip_list)

        while True:
            # stop if timeout is setted
            if args.totaltime is not None:
                time_now = time.time() - start_time
                if time_now > args.totaltime:
                    raise KeyboardInterrupt()
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
                        f.write(data)
            except Queue.Empty:
                # no matter - timeout finish before info come
                continue
    # my not very good way to exit :(
    except KeyboardInterrupt:
        logger.info("Finalization...")
        # kill our thread
        term_event.set()
        # wait for server termination
        server.join()
        # kill remote tool (if it is not killed yet)
        send_die_to_tools(ip_list, udp_sender, localy, args.localip)
    else:
        term_event.set()
        server.join()
        send_die_to_tools(ip_list, udp_sender, localy)


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



def copy_tool(ip_list, path, user, localy=False):
    """ Copy tool and libs to specified ips on path"""
    tool_names = ["perfcollect.py", "sysmets.py", "ceph_srv_info.py",
                  "sender.py", "packet.py", "logger.py", "ceph.py",
                  "daemonize.py", "umsgpack.py", "sh.py"]
    for ip in ip_list:
        for tool in tool_names:
            full_path = os.path.join(path, tool)
            cmd = "scp %s %s@%s:%s" % (tool, user, ip, full_path)
            execute(cmd)
    if localy:
        for tool in tool_names:
            full_path = os.path.join(path, tool)
            cmd = "cp {0} {1}".format(tool, full_path)
            execute(cmd)
            # p = psutil.Popen(cmd, shell=True)
            # p.wait()
            # if p.returncode != 0:
            #     logger = logging.getLogger(LOGGER_NAME)
            #     logger.error("Unsuccessfull copy to %s", ip)


def prepare_tool_cmd(args):
    """ Return params for tool start"""
    path = args.pathtotool
    port = args.port
    local_ip = args.localip
    part_size = args.partsize
    timeout = args.timeout
    sysmets = args.sysmetrics
    get_diff = args.diff

    # prepare args
    params = "-u UDP://%s:%s/%s -w %i" % (local_ip, port, part_size, timeout)
    if sysmets:
        params += " -m"
    if get_diff:
        params += " -d"

    cmd = "python %s/perfcollect.py %s" % (path, params)

    return cmd


def start_tool_localy(cmd):
    """ Start tool localy on current node """
    #psutil.Popen(cmd, shell=True)
    execute(cmd)


# @task
# @parallel
# def get_perfs_from_one_node(cmd):
#     """ Start local tool on node with specified params """
#     try:
#         run(cmd)
#     except KeyboardInterrupt:
#         # way to stop server
#         return


def get_perfs_from_all_nodes(user, cmd, ip_list):
    """ Start tool from path on every ip in ip_list
        Access by user, answer on port
        Return system metrics also, if sysmets=True """
    # # supress fabric output
    # with hide('output', 'running', 'warnings', 'status', 'aborts'):

    #     # setup fabric
    #     env.user = user
    #     env.hosts = ip_list

    #     tasks.execute(get_perfs_from_one_node, cmd=cmd)
    #     disconnect_all()
    for ip in ip_list:
        ssh = "ssh {0}@{1} {2}".format(user, ip, cmd)
        execute(ssh)

if __name__ == '__main__':
    exit(main(sys.argv))
