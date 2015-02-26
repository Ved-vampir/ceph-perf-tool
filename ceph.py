#!/usr/bin/env python
""" Ceph communications """

import json
import subprocess


import psutil


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
