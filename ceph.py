#!/usr/bin/env python
""" Ceph communications """

import json
import glob
import logging
from os.path import splitext, basename

import sh

from logger import define_logger


class CephException(Exception):
    """ Exceptions from ceph call"""
    pass

class ParameterException(Exception):
    """ Bad parameter in function"""
    pass


def get_osds_list():
    """ Get list of osds id"""
    try:
        res = sh.ceph.osd.ls()
        osd_list = [osd_id
                    for osd_id in res.split("\n") if osd_id != '']
        return osd_list
    except sh.CommandNotFound:
        logger = logging.getLogger(__name__)
        logger.error("Ceph command not found")
        raise CephException("Command not found")
    except:
        logger = logging.getLogger(__name__)
        logger.error("Ceph command 'osd ls' execution error")
        raise CephException("Execution error")


def get_mons_or_mds_ips(who):
    """ Return mon ip list """
    try:
        ips = set()
        if who == "mon":
            res = sh.ceph.mon.dump()
        elif who == "mds":
            res = sh.ceph.mds.dump()
        else:
            raise ParameterException("'%s' in get_mons_or_mds_ips instead of mon/mds" % who)

        line_res = res.split("\n")
        for line in line_res:
            fields = line.split()
            if len(fields) > 2 and who in fields[2]:
                ips.add(fields[1].split(":")[0])

        return ips

    except sh.CommandNotFound:
        logger = logging.getLogger(__name__)
        logger.error("Ceph command not found")
        raise CephException("Command not found")
    except ParameterException as e:
        logger = logging.getLogger(__name__)
        logger.error(e)
        raise e
    except:
        logger = logging.getLogger(__name__)
        mes = "Ceph command '%s dump' execution error" % who
        logger.error(mes)
        raise CephException("Execution error")


def get_osds_ips(osd_list):
    """ Get osd's ips """
    try:
        ips = set()
        for osd_id in osd_list:
            res = sh.ceph.osd.find(osd_id)
            ip = json.loads(str(res))["ip"]
            ips.add(ip.split(":")[0])
        return ips

    except sh.CommandNotFound:
        logger = logging.getLogger(__name__)
        logger.error("Ceph command not found")
        raise CephException("Command not found")
    except:
        logger = logging.getLogger(__name__)
        logger.error("Ceph command 'osd find' execution error")
        raise CephException("Execution error")


def get_socket_list(path):
    """ Returns list of sockets (ceph creatures) on node"""
    sock_list = [splitext(basename(sock))[0]
                 for sock in glob.glob(path + "*.asok")]
    return sock_list


def get_perf_data(socket_list, command, path):
    """ Basic command to return schemas or dumps
        of listed ceph creatures perfs"""
    logger = logging.getLogger(__name__)
    try:
        res = {}
        for sock in socket_list:
            try:
                cmd = "%s/%s.asok" % (path, sock)
                # if command == "dump":
                #     raw = sh.ceph.perf.dump(admin_daemon=cmd)
                # elif command == "schema":
                #     raw = sh.ceph.perf.schema(admin_daemon=cmd)
                # else:
                #     raise ParameterException("'%s' in get_perf_data"
                #                              " instead of dump/schema" % command)
                raw = sh.ceph(command, admin_daemon=cmd)
                res[sock] = json.loads(str(raw))
            except sh.ErrorReturnCode_22:
                # no such command for this daemon - it's normal,
                # because I don't filter commands by types (osd/mon)
                logger.warning("No command %s for socket %s", command, sock)

        return res

    except sh.CommandNotFound:
        logger.error("Ceph command not found")
        raise CephException("Command not found")
    except:
        logger.error("Ceph command '%s' execution error", cmd)
        raise CephException("Execution error")


define_logger(__name__)
