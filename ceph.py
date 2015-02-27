#!/usr/bin/env python
""" Ceph communications """

import json
import logging


import sh


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


def define_logger():
    """ Initialization of logger"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    formatter = logging.Formatter(log_format,
                                  "%H:%M:%S")
    ch.setFormatter(formatter)
    return logger


define_logger()
