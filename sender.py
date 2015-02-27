#!/usr/bin/env python
""" UDP sender class """

import socket
import logging
import urlparse

import packet


class SenderException(Exception):
    """ Exceptions in Sender class """
    pass


class Timeout(Exception):
    """ Exceptions in Sender class """
    pass


class Sender(object):
    """ UDP sender class """

    def __init__(self, url=None, port=None, host="127.0.0.1", size=256):
        """ Create connection object from input udp string or params"""

        logger = logging.getLogger(__name__)
        # test input
        if url is None and port is None:
            raise SenderException("Bad initialization")
        if url is not None:
            data = urlparse.urlparse(url)
            # check schema
            if data.scheme != "UDP":
                raise SenderException("Bad protocol type")
            # try to get port
            try:
                int_port = int(data.port)
            except ValueError:
                logger = logging.getLogger(__name__)
                logger.error("Bad UDP port")
                raise SenderException("Bad UDP port")
            # save paths
            self.sendto = (data.hostname, int_port)
            self.bindto = (data.hostname, int_port)
            # try to get size
            try:
                self.size = int(data.path.strip("/"))
            except ValueError:
                logger.error("Bad packet part size")
                raise SenderException("Bad packet part size")
        else:
            # url is None - use size and port
            self.sendto = (host, port)
            self.bindto = ("0.0.0.0", port)
            self.size = size

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.binded = False


    def bind(self):
        """ Prepare for listening """
        self.sock.bind(self.bindto)
        self.sock.settimeout(0.5)
        self.binded = True


    def send(self, data):
        """ Send data to udp socket"""
        if self.sock.sendto(data, self.sendto) != len(data):
            logger = logging.getLogger(__name__)
            mes = "Cannot send data to %s:%s" % self.sendto
            logger.error(mes)
            raise SenderException("Cannot send data")


    def send_by_protocol(self, data):
        """ Send data by Packet protocol"""
        parts = packet.Packet.create_packet(data, self.size)
        for part in parts:
            self.send(part)

    def recv(self):
        """ Receive data from udp socket"""
        # check for binding
        if not self.binded:
            self.bind()
        # try to recv
        try:
            data, (remote_ip, remote_port) = self.sock.recvfrom(self.size)
            return data, remote_ip
        except socket.timeout:
            raise Timeout()


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
