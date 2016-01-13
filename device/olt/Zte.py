#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pexpect
import sys
import configparser
import re
from funcy import re_all, partial, lmap
from funcy import filter

prompter = "#"
pager = "--More--"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read('config.ini')
username = config.get('olt', 'zte_username')
password = config.get('olt', 'zte_password')


def telnet(ip):
    child = pexpect.spawn(
        'telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile

    child.expect("[uU]sername:")
    child.sendline(username)
    child.expect("[pP]assword:")
    child.sendline(password)
    child.expect(prompter)
    return child


def doSome(child, cmd):
    result = []
    child.sendline(cmd)
    while True:
        index = child.expect([prompter, pager], timeout=120)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt = ''.join(result).replace(
        '\x08', '').replace(cmd + '\r\n', '', 1)
    return rslt


def getPonPorts(ip):
    try:
        child = telnet(ip)
        rslt = doSome(child, 'show run | in interface [eg]pon-olt')
        child.sendline('exit')
        child.close()
        rslt1 = re.split(r'\r\n\s*', rslt)[:-1]
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt1, ip)


def getPortOnus(child, port):
    rslt = doSome(child, 'show run {port}'.format(port=port))
    rslt1 = re_all(
        r'onu\s(\d+)\stype\sE8C[PG]24\sloid\s([A-F0-9]{16})', rslt)
    return (port, rslt1)


def getOnus(ip):
    mark, ports = getPonPorts(ip)[:-1]
    if mark == 'fail':
        return ('fail', None, ip)
    try:
        child = telnet(ip)
        gpo = partial(getPortOnus, child)
        rslt = lmap(gpo, ports)
        child.sendline('exit')
        child.close()
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt1 = filter(lambda x: bool(x[1]), rslt)
    return ('success', rslt1, ip)
