#!/usr/bin/env python
""" Module for system metrics collecting """

import ceph_srv_info


def get_system_metrics(ceph_socket_path):
    """ get memory, cpu and disk usage for all ceph processes"""
    met = {}

    srv_info = ceph_srv_info.get_ceph_srv_info(ceph_socket_path)
    for srv in srv_info:
        met[srv.name] = {}
        met[srv.name]["cpu"] = srv.cpu
        met[srv.name]["mem"] = srv.mem

    drv_info = ceph_srv_info.get_ceph_drv_info(ceph_socket_path)
    for disk in drv_info:
        met[disk.name] = {}
        met[disk.name]["read count"] = disk.rd_cnt
        met[disk.name]["write count"] = disk.wr_cnt
        met[disk.name]["read bytes"] = disk.rd_bytes
        met[disk.name]["write bytes"] = disk.wr_bytes
        met[disk.name]["read time"] = disk.rd_time
        met[disk.name]["write time"] = disk.wr_time

    return met
