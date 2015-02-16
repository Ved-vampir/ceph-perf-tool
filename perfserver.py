#!/usr/bin/env python

from __future__ import with_statement
import os
import json
import argparse
import subprocess
import socket
import threading
from fabric import tasks
from fabric.api import env, run, hide, settings, task
from fabric.network import disconnect_all


default_user = 'root'  # via him you enter the host
CEPH_RUN_NAME = os.getenv("CEPH_RUN_NAME", "ceph")  # ceph command name
MAX_WAIT_TIME = os.getenv("MAX_WAIT_TIME", 30)    # max answer waiting time in secs
PART_SIZE = os.getenv("PART_SIZE", 4096)    # size of part of packet


def listen_thread(port, con_count, filename):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))
    count = 0
    all_data = dict()
    while count < con_count:
        
        data, addr = sock.recvfrom(PART_SIZE)
        if (addr[0] in all_data):
            all_data[addr[0]][1] += data
            if (len(all_data[addr[0]][1]) == all_data[addr[0]][0]):
                count += 1
        else:
            s = data.partition("\n\r")
            all_data[addr[0]] = [int(s[0]), s[2]]

    if filename is None:
        for key, value in all_data.items():
            print value[1]
    else:
        with open(filename, 'w') as f:
            for key, value in all_data.items():
                f.write(value[1])


def main():  
    # parse command line
    ag = argparse.ArgumentParser(description="Server for collection perf counters from ceph nodes")
    ag.add_argument("--port", "-p", type=int, default=9095, help="Specify port for udp connection (9095 by default)")
    ag.add_argument("--user", "-u", type=str, default=default_user, help="User name for all hosts (root by default)")
    ag.add_argument("--pathtotool", "-t", type=str, required=True, help="Path to remote utility perfcollect.py")
    ag.add_argument("--savetofile", "-s", type=str, help="Save output in file, filename required")
    ag.add_argument("--sysmetrics", "-m", action="store_true", help="Include info about cpu, memory and disk usage")
    args = ag.parse_args()

    # find nodes
    osd_list = get_osds_list()
    ip_list = get_osds_ips(osd_list)

    # start socket listening
    server = threading.Thread(target=listen_thread, args=(args.port, len(ip_list), args.savetofile))
    server.start()

    # begin to collect counters

    print "Now waiting for answer..."
    get_perfs_from_all_nodes(args.pathtotool, args.port, args.user, ip_list, args.sysmetrics)

    server.join(MAX_WAIT_TIME)

    # if thread is alive, kill it
    if server.isAlive():
        print "No answer"
        server._Thread__stop()


# gets list of osds id
def get_osds_list():
    cmd = "%s osd ls" % (CEPH_RUN_NAME)
    PIPE = subprocess.PIPE
    p = subprocess.Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=subprocess.STDOUT)
    osd_list = [id for id in p.stdout.read().split("\n") if id != '']  # osd ids list
    return osd_list


# get osd's ips
def get_osds_ips(osd_list):
    ips = set()
    PIPE = subprocess.PIPE
    for osd_id in osd_list:
        cmd = "%s osd find %s" % (CEPH_RUN_NAME, osd_id)
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=subprocess.STDOUT)
        ips.add(json.loads(p.stdout.read())["ip"].split(":")[0])  # find hosts
    return ips


@task
def get_perfs_from_one_node(path, params):
    cmd = "python %s/perfcollect.py %s" % (path, params)
    result = run(cmd)
    return result


def get_perfs_from_all_nodes(path, port, user, ip_list, sysmets=False):
    with hide('output', 'running', 'warnings', 'status'):  
        
        # locate myself
        ip = socket.gethostbyname_ex(socket.gethostname())[2][0]

        # setup fabric
        env.user = user
        env.hosts = ip_list
 
        # prepare args
        params = "-u %s %i %i" % (ip, port, PART_SIZE)
        if sysmets:
            params += " -m"
        
        tasks.execute(get_perfs_from_one_node, path=path, params=params)

        # disconnect_all()

        # return perf_list


if __name__ == '__main__':
    main()
