#!/usr/bin/env python
""" Server for collecting performance data from all ceph nodes"""

import os
import sys
import json
import socket
import argparse
import threading
import subprocess
from fabric import tasks
from fabric.api import env, run, hide, task


# <koder>: make default command line option value
DEFAULT_USER = 'root'  # via him you enter the host

# <koder>: make a command line options from this params
# <koder>: and pass them explicitly
CEPH_RUN_NAME = os.getenv("CEPH_RUN_NAME", "ceph")  # ceph command name
MAX_WAIT_TIME = os.getenv("MAX_WAIT_TIME", 30)  # max answer waiting time (sec)
PART_SIZE = os.getenv("PART_SIZE", 4096)    # size of part of packet


def listen_thread(port, con_count, filename=None):
    """ Main listenig thread for socket
        Listen port, while waiting con_count answers
        Write answers to stdout or to file, if it specified """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    count = 0
    all_data = {}

    while count < con_count:

        # <koder>: remote_ip, remote_port = addr
        # <koder>: all this [0][0] doesn't looks really good
        data, addr = sock.recvfrom(PART_SIZE)
        if addr[0] in all_data:
            # <koder>: make shortcut for all_data[addr[0]]
            all_data[addr[0]][1] += data
            if len(all_data[addr[0]][1]) == all_data[addr[0]][0]:
                count += 1
        else:
            s = data.partition("\n\r")
            all_data[addr[0]] = [int(s[0]), s[2]]

    # <koder>: can we move IO outside this thread?
    if filename is None:
        for key, value in all_data.items():
            print value[1]
    else:
        with open(filename, 'w') as f:
            for key, value in all_data.items():
                f.write(value[1])


def parse_command_args(argv):
    """ Command line argument parsing """
    ag = argparse.ArgumentParser(description="Server for collecting"
                                             " perf counters from ceph nodes")
    ag.add_argument("--port", "-p", type=int, default=9095,
                    help="Specify port for udp connection (9095 by default)")
    ag.add_argument("--user", "-u", type=str, default=DEFAULT_USER,
                    help="User name for all hosts (root by default)")
    ag.add_argument("--pathtotool", "-t", type=str, required=True,
                    help="Path to remote utility perfcollect.py")
    ag.add_argument("--savetofile", "-s", type=str,
                    help="Save output in file, filename required")
    ag.add_argument("--sysmetrics", "-m", action="store_true",
                    help="Include info about cpu, memory and disk usage")
    return ag.parse_args(argv)


def main(argv):
    """ Server starts from here """
    # parse command line
    args = parse_command_args(argv[1:])

    # find nodes
    osd_list = get_osds_list()
    ip_list = get_osds_ips(osd_list)

    # start socket listening
    server = threading.Thread(target=listen_thread,
                              args=(args.port, len(ip_list), args.savetofile))
    server.start()

    # begin to collect counters

    print "Now waiting for answer..."
    get_perfs_from_all_nodes(args.pathtotool, args.port, args.user,
                             ip_list, args.sysmetrics)

    server.join(MAX_WAIT_TIME)

    # if thread is alive, kill it
    # <koder>: create a control mechanism to force thread to exit
    # <koder>: like conditional variable, or queue
    if server.isAlive():
        print "No answer"
        # <koder>: never use such call
        # <koder>: make thread a daemon and exits
        server._Thread__stop()


def get_osds_list():
    """ Get list of osds id"""
    # <koder>: replace with psutils
    cmd = "%s osd ls" % (CEPH_RUN_NAME)
    PIPE = subprocess.PIPE
    p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                         stdout=PIPE, stderr=subprocess.STDOUT)
    osd_list = [osd_id
                for osd_id in p.stdout.read().split("\n") if osd_id != '']
    return osd_list


def get_osds_ips(osd_list):
    """ Get osd's ips """
    # <koder>: replace with psutils
    ips = set()
    PIPE = subprocess.PIPE
    for osd_id in osd_list:
        cmd = "%s osd find %s" % (CEPH_RUN_NAME, osd_id)
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                             stdout=PIPE, stderr=subprocess.STDOUT)

        ip = json.loads(p.stdout.read())["ip"]
        ips.add(ip.split(":")[0])
    return ips


@task
def get_perfs_from_one_node(path, params):
    """ Start local tool on node with specified params """
    # <koder>: don't we need to copy this file to node first?
    cmd = "python %s/perfcollect.py %s" % (path, params)
    result = run(cmd)
    return result


def get_perfs_from_all_nodes(path, port, user, ip_list, sysmets=False):
    """ Start tool from path on every ip in ip_list
        Access by user, answer on port
        Return system metrics also, if sysmets=True """
    # supress fabric output
    with hide('output', 'running', 'warnings', 'status'):

        # locate myself
        # <koder>: you know - this might not works. We need to define more
        # appropriate code to define ip or, better, request user for it
        local_ip = socket.gethostbyname_ex(socket.gethostname())[2][0]

        # setup fabric
        env.user = user
        env.hosts = ip_list

        # prepare args
        params = "-u %s %i %i" % (local_ip, port, PART_SIZE)
        if sysmets:
            params += " -m"

        tasks.execute(get_perfs_from_one_node, path=path, params=params)


if __name__ == '__main__':
    exit(main(sys.argv))
