#!/usr/bin/env python
""" Server for collecting performance data from all ceph nodes"""

import os
import sys
import json
import Queue
import socket
import argparse
import threading
import subprocess


import psutil
from fabric import tasks
from fabric.api import env, run, hide, task, parallel
from fabric.network import disconnect_all

import packet


def listen_thread(port, con_count, part_size, result, term_event):
    """ Main listenig thread for socket
        Listen port, while waiting con_count answers
        Write answers to stdout or to file, if it specified """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(5)
    count = 0
    all_data = {}

    while True: #count < con_count:

        try:
            data, addr = sock.recvfrom(part_size)
            remote_ip, remote_port = addr

            if remote_ip not in all_data:
                all_data[remote_ip] = packet.Packet()

            ready = all_data[remote_ip].new_packet(data)

            if ready is not None:
                result.put(ready)

            # if remote_ip in all_data:

            #     cur_data = all_data[remote_ip]
            #     cur_data[1] += data
            #     if len(cur_data[1]) == cur_data[0]:
            #         count += 1

            # else:
            #     s = data.partition("\n\r")
            #     all_data[remote_ip] = [int(s[0]), s[2]]

        except socket.timeout:
            # no answer yet - check, if server want to kill us
            if term_event.is_set():
                break

    # # put result in queue without tech info
    # if count == con_count:
    #     # if we finished by itself - return all
    #     result.put([value[1] for key, value in all_data.items()])
    # else:
    #     # if result is not full, return only full answers
    #     result.put([value[1]
    #                 for key, value in all_data.items()
    #                 if value[0] == len(value[1])])


def parse_command_args(argv):
    """ Command line argument parsing """
    ag = argparse.ArgumentParser(description="Server for collecting"
                                             " perf counters from ceph nodes")
    # block with default values
    ag.add_argument("--port", "-p", type=int,
                    default=9095,
                    help="Specify port for udp connection (9095 by default)")
    ag.add_argument("--user", "-u", type=str,
                    default="root",
                    help="User name for all hosts (root by default)")
    ag.add_argument("--timeout", "-w", type=int,
                    default=30,
                    help="Max time in sec waiting for answers (30 by default)")
    ag.add_argument("--partsize", "-b", type=int,
                    default=4096,
                    help="Part size for udp packet (4096 by default)")
    ag.add_argument("--ceph", "-c", type=str,
                    default="ceph",
                    help="Ceph command line command (ceph by default)")
    # required params
    ag.add_argument("--pathtotool", "-t", type=str, required=True,
                    help="Path to remote utility perfcollect.py")
    # params with value
    ag.add_argument("--savetofile", "-s", type=str,
                    help="Save output in file, filename required")
    ag.add_argument("--localip", "-i", type=str,
                    help="Local ip for udp answer (if you don't specify it,"
                         " not good net might be used)")
    # flag params
    ag.add_argument("--sysmetrics", "-m", action="store_true",
                    help="Include info about cpu, memory and disk usage")
    ag.add_argument("--copytool", "-y", action="store_true",
                    help="Copy tool to all nodes to path from -t")

    return ag.parse_args(argv)


def main(argv):
    """ Server starts from here """
    # parse command line
    args = parse_command_args(argv[1:])

    # find nodes
    osd_list = get_osds_list(args.ceph)
    ip_list = get_osds_ips(osd_list, args.ceph)

    # copy tool, if user want
    if args.copytool:
        copy_tool(ip_list, args.pathtotool, args.user)

    # start socket listening
    result = Queue.Queue()
    term_event = threading.Event()
    server = threading.Thread(target=listen_thread,
                              args=(args.port, len(ip_list), args.partsize,
                                    result, term_event))
    try:
        server.start()

        # begin to collect counters

        print "Now waiting for answer..."
        tools = threading.Thread(target=get_perfs_from_all_nodes,
                                 args=(args.pathtotool, args.port, args.user,
                                       ip_list, args.localip, args.partsize,
                                       args.sysmetrics))
        tools.start()

        while True:
            # without any timeout KeyboardInterrupt will not raise
            really_big_timeout = sys.maxint
            data = result.get(timeout=really_big_timeout)
            # proceed returned data
            if args.savetofile is None:
                print data
            else:
                with open(args.savetofile, 'a') as f:
                    f.write(data)
    # my not very good way to exit :(
    except KeyboardInterrupt:
        print "Finalization..."
        # kill our thread
        term_event.set()
        # kill remote tool (if it is not killed yet)
        send_die_to_tools(ip_list, args.port)
    else:
        term_event.set()
        send_die_to_tools(ip_list, args.port)


def send_die_to_tools(ip_list, port):
    """ Send message to die to tools"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for ip in ip_list:
        sock.sendto("Time to die", (ip, port))


def copy_tool(ip_list, path, user):
    """ Copy tool to specified ips on path"""
    tool_name = "perfcollect.py"
    full_path = os.path.join(path, tool_name)
    for ip in ip_list:
        cmd = "scp %s %s@%s:%s" % (tool_name, user, ip, full_path)
        p = psutil.Popen(cmd, shell=True)
        p.wait()
        if p.returncode != 0:
            print "Unsuccessfull copy to ", ip


def get_osds_list(ceph_run_name):
    """ Get list of osds id"""
    # <koder>: replace with psutils
    cmd = "%s osd ls" % (ceph_run_name)
    PIPE = subprocess.PIPE
    p = psutil.Popen(cmd, shell=True, stdout=PIPE)
    res, err = p.communicate()
    osd_list = [osd_id
                for osd_id in res.split("\n") if osd_id != '']
    return osd_list


def get_osds_ips(osd_list, ceph_run_name):
    """ Get osd's ips """
    # <koder>: replace with psutils
    ips = set()
    PIPE = subprocess.PIPE
    for osd_id in osd_list:
        cmd = "%s osd find %s" % (ceph_run_name, osd_id)
        p = psutil.Popen(cmd, shell=True, stdout=PIPE)
        res, err = p.communicate()
        if err is None:
            ip = json.loads(res)["ip"]
            ips.add(ip.split(":")[0])
    return ips


@task
@parallel
def get_perfs_from_one_node(path, params):
    """ Start local tool on node with specified params """
    # <koder>: don't we need to copy this file to node first?
    # <I>: not always, separate func created
    try:
        cmd = "python %s/perfcollect.py %s" % (path, params)
        run(cmd)
    except KeyboardInterrupt:
        # way to stop server
        return


def get_perfs_from_all_nodes(path, port, user, ip_list, local_ip,
                             part_size, sysmets=False):
    """ Start tool from path on every ip in ip_list
        Access by user, answer on port
        Return system metrics also, if sysmets=True """
    # supress fabric output
    with hide('output', 'running', 'warnings', 'status', 'aborts'):

        # locate myself
        if local_ip is None:
            local_ip = socket.gethostbyname_ex(socket.gethostname())[2][0]

        # setup fabric
        env.user = user
        env.hosts = ip_list

        # prepare args
        params = "-u %s %i %i -w %i" % (local_ip, port, part_size, 5)
        if sysmets:
            params += " -m"

        tasks.execute(get_perfs_from_one_node, path=path, params=params)
        disconnect_all()

if __name__ == '__main__':
    exit(main(sys.argv))
