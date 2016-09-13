#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pexpect
import configparser
import sys
import re
import os
from functools import reduce
from funcy import re_all, ldistinct, re_find, lmap, partial
from funcy import re_find, select
import time
import easysnmp

pager = "--More--"
prompter = "#"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read(os.path.expanduser('~/.weihu/config.ini'))
username = config.get('switch', 'username')
password = config.get('switch', 'passwd')
super_password = config.get('switch', 'super_passwd')
community_read = config.get('switch', 'community')


def telnet(ip):
    child = pexpect.spawn(
        'telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile

    child.expect('Username:')
    child.sendline(username)
    child.expect('Password:')
    child.sendline(password)
    index = child.expect(['>', '#'])
    if index == 0:
        child.sendline('enable')
        child.expect('Password:')
        child.sendline(super_password)
        child.expect('#')
    return child


def do_some(child, command):
    result = []
    child.sendline(command)
    while True:
        index = child.expect([prompter, pager], timeout=120)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt = ''.join(result).replace('\x08', '')
    return rslt.replace(command + '\r\n', '', 1)


def close(child):
    child.sendcontrol('z')
    child.expect('#')
    child.sendline('exit')
    child.close()


def get_groups(ip):
    def _get_desc(child, group):
        name = group['name']
        rslt = do_some(child, 'show run interface {name}'.format(name=name))
        desc = re_find(r'description\s(\S+ *\S*)', rslt)
        mode = re_find(r'smartgroup mode (\S+)', rslt)
        if mode == '802.3ad':
            mode = 'yes'
        group['desc'] = desc
        group['mode'] = mode
        return group

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show lacp internal')
        temp = re_all(r'Smartgroup:(\d+)', rslt)
        temp1 = [dict(name='smartgroup' + x)
                 for x in temp]
        groups = lmap(partial(_get_desc, child), temp1)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', groups, ip)


def get_infs(ip):
    def _get_desc(child, inf):
        name = inf['name']
        rslt = do_some(child, 'show run interface {name}'.format(name=name))
        desc = re_find(r'description\s(\S+ *\S*)', rslt)
        group = re_find(r'(smartgroup\s\d+)', rslt)
        if group is not None:
            group = group.replace(' ', '')
        inf['desc'] = desc
        inf['group'] = group
        return inf

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show run | in interface (xg|g)ei_')
        temp = [dict(name=x)
                for x in re_all(r'interface\s(\S+)', rslt)]
        infs = lmap(partial(_get_desc, child), temp)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', infs, ip)


def get_infs_bySnmp(ip):
    def _get_infs(oid):
        index = oid.value
        desc = 'None'
        name = session.get(('ifDescr', index)).value
        if ' ' in name:
            name, desc = name.split(' ', 1)
        state = session.get(('ifOperStatus', index)).value
        if state == '1':
            state = 'up'
        else:
            state = 'down'
        bw = int(session.get(('ifSpeed', index)).value or 0)
        collTime = time.time()
        inCount = int(session.get(('ifInOctets', index)).value or 0)
        outCount = int(session.get(('ifOutOctets', index)).value or 0)
        return dict(name=name, desc=desc, state=state, bw=bw,
                    inCount=inCount, outCount=outCount, collTime=collTime)

    try:
        session = easysnmp.Session(
            hostname=ip, community=community_read, version=1)
        indexs = session.walk('ifIndex')
        rslt = lmap(_get_infs, indexs)
        return ('success', rslt, ip)
    except (easysnmp.EasySNMPTimeoutError) as e:
        return ('fail', None, ip)


def get_traffics(ip, infs):
    def _get_traffic(child, inf):
        rslt = do_some(child, 'show interface {inf}'.format(inf=inf))
        state = re_find(r'{inf}\sis\s(\w+\s?\w*)'.format(inf=inf),
                        rslt).lower()
        bw = int(re_find(r'BW\s(\d+)\sKbits', rslt)) / 1000
        inTraffic = int(
            re_find(r'120 seconds input.*:\s+(\d+)\sBps', rslt)) * 8 / 1000000
        outTraffic = int(
            re_find(r'120 seconds output.*:\s+(\d+)\sBps', rslt)) * 8 / 1000000
        infDict = dict(name=inf, state=state, bw=bw,
                       inTraffic=inTraffic, outTraffic=outTraffic)
        return infDict

    try:
        child = telnet(ip)
        rslt = lmap(partial(_get_traffic, child), infs)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt, ip)


def get_vlans(ip):
    def _vlan(v):
        if '-' in v:
            s, e = [int(x) for x in v.split('-')]
        else:
            s = e = int(v)
        return range(s, e + 1)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show run | in (hybrid|trunk) vlan')
        close(child)
        vlans = re_all(r'vlan\s(\d+(?:-\d+)?)', rslt)
        vlans = reduce(lambda x, y: x | set(_vlan(y)), vlans, set())
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', list(vlans), ip)


def get_ports(ip):
    def _get_info(record):
        name = re_find(r'((?:xg|g|f)ei\S+) is \w+ ?\w+,', record)
        state = re_find(r'(?:xg|g|f)ei\S+ is (\w+ ?\w+),', record)
        desc = re_find(r'Description is (\S+ *\S+)', record)
        inTraffic = int(
            re_find(r'120 seconds input.*:\s+(\d+)\sBps', record) or 0) * 8 / 1000000
        outTraffic = int(
            re_find(r'120 seconds output.*:\s+(\d+)\sBps', record) or 0) * 8 / 1000000
        return dict(name=name, desc=desc, state=state, inTraffic=inTraffic, outTraffic=outTraffic)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show interface')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt = re.split(r'\r\n *\r\n', rslt)
    rslt = select(lambda x: bool(x['name']),
                  lmap(_get_info, rslt))
    return ('success', rslt, ip)


def get_main_card(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'show version')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    temp = re_all(r'MEC\d,\spanel\s\d,\s(?:slave|master)', rslt)
    return ('success', len(temp), ip)


def get_power_info(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'show powerfanstate')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    temp = re_all(r'Power\d\s+:\sNormal Work', rslt)
    return ('success', len(temp), ip)


def no_shut(ip, inf):
    try:
        child = telnet(ip)
        do_some(child, 'conf t')
        do_some(child, 'interface {inf}'.format(inf=inf))
        do_some(child, 'no shutdown')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', ip)
    return ('success', ip)


def get_inf(ip, inf):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'show interface {inf}'.format(inf=inf))
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT):
        return ('fail', None, ip)
    state = re_find(r'is (\w+\s?\w+)', rslt)
    return ('success', state, ip)
