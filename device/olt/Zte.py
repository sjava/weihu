#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pexpect
import sys
import configparser
import re
from funcy import re_all, partial, lmap, re_find
from funcy import select, distinct, filter
from toolz import thread_last

prompter = "#"
pager = "--More--"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read('config.ini')
username = config.get('olt', 'zte_username')
password = config.get('olt', 'zte_password')


def telnet(ip):
    child = pexpect.spawn('telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile

    child.expect("[uU]sername:")
    child.sendline(username)
    child.expect("[pP]assword:")
    child.sendline(password)
    child.expect(prompter)
    return child


def do_some(child, cmd, timeout=120):
    result = []
    child.sendline(cmd)
    while True:
        index = child.expect([prompter, pager], timeout=timeout)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt = ''.join(result).replace('\x08', '').replace(cmd + '\r\n', '', 1)
    return rslt


def close(child):
    child.sendcontrol('z')
    child.expect(prompter)
    child.sendline('exit')
    child.close()


def get_pon_ports(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'show run | in interface [eg]pon-olt')
        child.sendline('exit')
        child.close()
        rslt1 = re.split(r'\r\n\s*', rslt)[:-1]
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt1, ip)


def get_port_onus(child, port):
    rslt = do_some(child, 'show run {port}'.format(port=port))
    rslt1 = re_all(r'onu\s(\d+)\stype\sE8C[PG]24\sloid\s([A-F0-9]{16})', rslt)
    return (port, rslt1)


def get_onus(ip):
    mark, ports = get_pon_ports(ip)[:-1]
    if mark == 'fail':
        return ('fail', None, ip)
    try:
        child = telnet(ip)
        gpo = partial(get_port_onus, child)
        rslt = lmap(gpo, ports)
        child.sendline('exit')
        child.close()
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt1 = filter(lambda x: bool(x[1]), rslt)
    return ('success', rslt1, ip)


def get_groups(ip):
    def _get_infs(record):
        name = re_find(r'(Smartgroup:\d+)', record)
        if name:
            name = name.lower().replace(':', '')
        infs = re_all(r'(x?gei_\d+/\d+/\d+)\s?selected', record)
        return dict(name=name, infs=infs)

    def _get_desc_mode(child, group):
        rslt = do_some(child, 'show run int {name}'.format(name=group['name']))
        desc = re_find(r'description\s+(\S+)', rslt)
        group['desc'] = desc
        rslt = do_some(child, 'show run int {inf}'.format(inf=group['infs'][0]))
        mode = re_find(r'smartgroup\s\d+\smode\s(\S+)', rslt)
        group['mode'] = mode
        return group

    try:
        child = telnet(ip)
        rslt = re.split(r'\r\n\s*\r\n', do_some(child, 'show lacp internal'))
        groups = thread_last(rslt,
                             (lmap, _get_infs),
                             (select, lambda x: x['name'] and x['infs']))
        lmap(partial(_get_desc_mode, child), groups)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', groups, ip)


def get_infs(ip):
    def _get_info(child, inf):
        rslt = do_some(child, 'show int {inf}'.format(inf=inf))
        desc = re_find(r'Description\sis\s(\S+)', rslt)
        state = re_find(r'{inf}\sis\s(\S+\s?\S+),'.format(inf=inf), rslt)
        bw = re_find(r'BW\s(\d+)\sKbits', rslt)
        bw = int(bw or 0) / 1000
        inTraffic = re_find(r'seconds\sinput\srate\s?:\s+(\d+)\sBps', rslt)
        inTraffic = int(inTraffic or 0) * 8 / 1e6
        outTraffic = re_find(r'seconds\soutput\srate:\s+(\d+)\sBps', rslt)
        outTraffic = int(outTraffic or 0) * 8 / 1e6
        return dict(name=inf, desc=desc, state=state, bw=bw,
                    inTraffic=inTraffic, outTraffic=outTraffic)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show run | in interface', timeout=180)
        rslt = re_all(r'interface\s+(x?gei_\d+/\d+/\d+)', rslt)
        infs = lmap(partial(_get_info, child), rslt)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', infs, ip)
