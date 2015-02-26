#!/usr/bin/env python

import os
import glob
import json
import subprocess
import os.path

import psutil


class CEPHSrvInfo(object):
    def __init__(self, name, pid, cpu=0, mem=0):
        self.name = name
        self.pid = pid
        self.cpu = cpu
        self.mem = mem

    def __str__(self):
        templ = '<Service {0.name}: pid={0.pid},' + \
                'cpu={0.cpu}%, mem={0.mem}B>'
        return templ.format(self)


class CEPHDiskInfo(object):
    def __init__(self, name, rd_cnt=0, wr_cnt=0, rd_bytes=0,
                 wr_bytes=0, rd_time=0, wr_time=0):
        self.name = name
        self.rd_cnt = rd_cnt
        self.wr_cnt = wr_cnt
        self.rd_bytes = rd_bytes
        self.wr_bytes = wr_bytes
        self.rd_time = rd_time
        self.wr_time = wr_time

    def __str__(self):
        message = 'DISK {0.name}: read count {0.rd_cnt}' + \
                  ', write count {0.wr_cnt}' + \
                  ', read bytes {0.rd_bytes}' + \
                  ', write bytes {0.wr_bytes}' + \
                  ', read time {0.rd_time}' + \
                  ', write time {0.wr_time}'
        return message.format(self)


def get_ceph_srv_info(ceph_socket_path = '/var/run/ceph/'):
    """ Return list of CEPHSrvInfo for all CEPH services on the local node """
    services = []
    for name, pid in get_ceph_pids(ceph_socket_path):
        process = psutil.Process(pid)
        services.append(CEPHSrvInfo(name,
                                    pid,
                                    process.get_cpu_percent(),
                                    process.memory_info().rss))
    return services


def get_ceph_drv_info(ceph_socket_path = '/var/run/ceph/'):
    """ Return list of CEPHDiskInfo for all disks that used by CEPH on the
        local node
    """
    disks_info = []
    stat = psutil.disk_io_counters(perdisk=True)
    for drv in get_ceph_disk(ceph_socket_path):
        info = CEPHDiskInfo(drv)
        disk = os.path.basename(drv)
        if disk in stat:
            info.rd_cnt = stat[disk].read_count
            info.wr_cnt = stat[disk].write_count
            info.rd_bytes = stat[disk].read_bytes
            info.wr_bytes = stat[disk].write_bytes
            info.rd_time = stat[disk].read_time
            info.wr_time = stat[disk].write_time

        disks_info.append(info)

    return disks_info


def get_ceph_pids(ceph_socket_path = '/var/run/ceph/'):
    """ Return list tuple (NAME, PID) as list of SrvInfo for all CEPH
        services on local node.
    """
    pids = []
    for srv in get_srv_list(ceph_socket_path):
        cfg = get_srv_config(ceph_socket_path, srv)
        with open(cfg['pid_file'], 'r') as file_fd:
            pids.append((srv, int(file_fd.read())))
    return pids


def get_ceph_disk(ceph_socket_path = '/var/run/ceph/'):
    """ Return list of disk devices wich is used by all
        CEPH services on local node.
    """
    disks = []
    for srv in get_srv_list(ceph_socket_path):
        cfg = get_srv_config(ceph_socket_path, srv)
        for key in ['osd_data', 'osd_journal', 'mds_data', 'mon_data']:
            mnt_point = cfg[key]
            disk = get_disk_by_mountpoint(find_mount_point(mnt_point))
            if disk not in disks:
                disks.append(disk)
    return disks


def get_srv_list(ceph_socket_path):
    """ Returns list of srv (ceph creatures) on node """
    return [os.path.splitext(os.path.basename(sock))[0]
            for sock in glob.glob(ceph_socket_path + "*.asok")]


def get_srv_config(ceph_socket_path, name):
    """ Get CEPH Service Config """
    cmd = "ceph --admin-daemon %s/%s.asok config show" % \
        (ceph_socket_path, name)
    try:
        raw_out = eval(subprocess.check_output(cmd, shell=True))
    except AttributeError:
        # hack for python < 2.6
        PIPE = subprocess.PIPE
        p = subprocess.Popen(cmd, shell=True, stdin=PIPE,
                             stdout=PIPE, stderr=subprocess.STDOUT)
        raw_out = p.stdout.read()

    return json.loads(raw_out)


def get_disk_by_mountpoint(mnt_point):
    """ Return disk of mountpoint """
    diskparts = psutil.disk_partitions()
    for item in diskparts:
        if item.mountpoint == mnt_point:
            return os.path.realpath(item.device)

    raise OSError("Can't define disk for {0!r}".format(mnt_point))


def find_mount_point(path):
    """ Find mount point by provided path """
    path = os.path.abspath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def test():
    ceph_socket_path = os.getenv("CEPH_RUN_PATH", "/var/run/ceph/")
    for srv in get_ceph_srv_info(ceph_socket_path):
        print str(srv)

    for disk in get_ceph_drv_info(ceph_socket_path):
        print str(disk)


if __name__ == '__main__':
    test()
