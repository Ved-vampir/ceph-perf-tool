#!/usr/bin/env python
""" Module for system metrics collecting """

# <koder>: std modules first
import subprocess


# <koder>: than 3rd party
import psutil


# improved version
def get_ceph_proc_list1():
    """ find ceph processes, pids list return"""
    pids = {}
    for proc in psutil.process_iter():
        try:
            pinfo = proc.as_dict(attrs=['pid', 'name', 'cmdline'])
        except psutil.NoSuchProcess:
            pass
        else:
            if "ceph" in pinfo['name']:

                i_flag = False
                name = ""
                for arg in pinfo['cmdline']:
                    # find for ceph creature name in command line
                    if i_flag:
                        name = arg
                        break
                    if arg == "-i":
                        i_flag = True

                name = "%s.%s" % (pinfo['name'], name)
                pids[name] = pinfo['pid']

    return pids


def get_ceph_proc_list():
    """ find ceph processes, pids list return"""

    # <koder>: replace subprocess.Popen with
    # <koder>: https://pythonhosted.org/psutil/#process-class
    cmd = "ps aux | grep ceph"
    PIPE = subprocess.PIPE
    p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                         stdout=PIPE, stderr=subprocess.STDOUT)
    res = p.stdout.read().split("\n")
    pids = {}
    for r in res:
        if r:
            s = r.split()
            # <koder>: magic numbers??
            if "ceph" in s[10]:
                s = r.split()
                # <koder>: magic numbers??
                proc_name = "%s-%s" % (s[10], s[12])
                pids[proc_name] = int(s[1])

    return pids


def get_system_metrics():
    """ get memory, cpu and disk usage for all ceph processes"""

    mets = {}
    for name, pid in get_ceph_proc_list1().items():
        p = psutil.Process(pid)
        mets[name] = p.as_dict(attrs=['io_counters',
                                      'cpu_times',
                                      'cpu_percent',
                                      'memory_info_ex',
                                      'memory_percent'])

    return mets



if __name__ == '__main__':
    print get_system_metrics()
