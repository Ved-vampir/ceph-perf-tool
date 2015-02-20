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


def listen_thread(port, part_size, result, term_event):
    """ Main listenig thread for socket
        Listen port, while waiting con_count answers
        Write answers to stdout or to file, if it specified """

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(5)
    all_data = {}

    while True: 

        try:
            data, addr = sock.recvfrom(part_size)
            remote_ip, remote_port = addr

            if remote_ip not in all_data:
                all_data[remote_ip] = packet.Packet()

            ready = all_data[remote_ip].new_packet(data)

            if ready is not None:
                result.put(ready)

        except socket.timeout:
            # no answer yet - check, if server want to kill us
            if term_event.is_set():
                break


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
                    default=5,
                    help="Time between collecting (5 by default)")
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
    ag.add_argument("--diff", "-d", action="store_true",
                    help="Get not counters values, but their difference "
                         "time by time")
    ag.add_argument("--copytool", "-y", action="store_true",
                    help="Copy tool to all nodes to path from -t")

    return ag.parse_args(argv)


def main(argv):
    """ Server starts from here """
    # parse command line
    args = parse_command_args(argv[1:])

    # find nodes
    osd_list = get_osds_list(args.ceph)
    osd_ip_list = get_osds_ips(osd_list, args.ceph)
    mon_ip_list = get_mons_or_mds_ips(args.ceph, "mon")
    mds_ip_list = get_mons_or_mds_ips(args.ceph, "mds")
    ip_list = osd_ip_list | mon_ip_list | mds_ip_list


    # copy tool, if user want
    if args.copytool:
        copy_tool(ip_list, args.pathtotool, args.user)

    # start socket listening
    result = Queue.Queue()
    term_event = threading.Event()
    server = threading.Thread(target=listen_thread,
                              args=(args.port, args.partsize,
                                    result, term_event))
    try:
        server.start()

        # begin to collect counters

        print "Now waiting for answer... Use Ctrl+C for exit."

        # supress connection to localhost
        cmd = prepare_tool_cmd(args)
        if "127.0.0.1" in ip_list:
            start_tool_localy(cmd)
            ip_list.remove("127.0.0.1")

        tools = threading.Thread(target=get_perfs_from_all_nodes,
                                 args=(args.user, cmd, ip_list))
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
        send_die_to_tools(ip_list, args.port+1)
    else:
        term_event.set()
        send_die_to_tools(ip_list, args.port+1)


def send_die_to_tools(ip_list, port):
    """ Send message to die to tools"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for ip in ip_list:
        sock.sendto("Time to die", (ip, port))


def copy_tool(ip_list, path, user):
    """ Copy tool and libs to specified ips on path"""
    tool_names = ["perfcollect.py", "sysmets.py", "ceph_srv_info.py"]
    for ip in ip_list:
        for tool in tool_names:
            full_path = os.path.join(path, tool)
            cmd = "scp %s %s@%s:%s" % (tool, user, ip, full_path)
            p = psutil.Popen(cmd, shell=True)
            p.wait()
            if p.returncode != 0:
                print "Unsuccessfull copy to ", ip


def get_osds_list(ceph_run_name):
    """ Get list of osds id"""
    cmd = "%s osd ls" % (ceph_run_name)
    PIPE = subprocess.PIPE
    p = psutil.Popen(cmd, shell=True, stdout=PIPE)
    res, err = p.communicate()
    osd_list = [osd_id
                for osd_id in res.split("\n") if osd_id != '']
    return osd_list


def get_mons_or_mds_ips(ceph_run_name, who):
    """ Return mon ip list """
    ips = set()
    cmd = "%s mon dump" % (ceph_run_name)
    PIPE = subprocess.PIPE
    p = psutil.Popen(cmd, shell=True, stdout=PIPE)
    res, err = p.communicate()
    if err is None:
        line_res = res.split("\n")
        for line in line_res:
            fields = line.split()
            if len(fields) > 2 and who in fields[2]:
                ips.add(fields[1].split(":")[0])

    return ips


def get_osds_ips(osd_list, ceph_run_name):
    """ Get osd's ips """
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


def prepare_tool_cmd(args):
    """ Return params for tool start"""
    path = args.pathtotool
    port = args.port
    local_ip = args.localip
    part_size = args.partsize
    timeout = args.timeout
    sysmets = args.sysmetrics
    get_diff = args.diff

    # locate myself
    if local_ip is None:
        local_ip = socket.gethostbyname_ex(socket.gethostname())[2][0]

    # prepare args
    params = "-u %s %i %i -w %i" % (local_ip, port, part_size, timeout)
    if sysmets:
        params += " -m"
    if get_diff:
        params += " -d"

    cmd = "python %s/perfcollect.py %s" % (path, params)
    return cmd


def start_tool_localy(cmd):
    """ Start tool localy on current node """

@task
@parallel
def get_perfs_from_one_node(cmd):
    """ Start local tool on node with specified params """
    try:
        run(cmd)
    except KeyboardInterrupt:
        # way to stop server
        return


def get_perfs_from_all_nodes(user, cmd, ip_list):
    """ Start tool from path on every ip in ip_list
        Access by user, answer on port
        Return system metrics also, if sysmets=True """
    # supress fabric output
    with hide('output', 'running', 'warnings', 'status', 'aborts'):

        # setup fabric
        env.user = user
        env.hosts = ip_list

        tasks.execute(get_perfs_from_one_node, cmd=cmd)
        disconnect_all()

if __name__ == '__main__':
    exit(main(sys.argv))
