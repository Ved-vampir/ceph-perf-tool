#!/usr/bin/env python
""" Module for system metrics collecting """

import psutil
import subprocess


def get_ceph_proc_list():
    """ find ceph processes, pids list return"""
    cmd = "ps aux | grep ceph"
    PIPE = subprocess.PIPE
    p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                         stdout=PIPE, stderr=subprocess.STDOUT)
    res = p.stdout.read().split("\n")
    pids = dict()
    for r in res:
        if r:
            s = r.split()
            if "ceph" in s[10]:
                s = r.split()
                proc_name = "%s-%s" % (s[10], s[12])
                pids[proc_name] = int(s[1])

    return pids


def get_system_metrics():
    """ get memory, cpu and disk usage for all ceph processes"""
    pids = get_ceph_proc_list()

    mets = dict()
    for name, pid in pids.items():
        p = psutil.Process(pid)
        mets[name] = p.as_dict(attrs=['io_counters',
                                      'cpu_times',
                                      'cpu_percent',
                                      'memory_info_ex',
                                      'memory_percent'])

    return mets
