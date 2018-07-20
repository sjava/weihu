#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import os
import re
import time
import easysnmp
from functools import reduce
from funcy import lmap, map, re_find, re_all, rcompose, filter
from funcy import select, partial, re_test, lconcat, autocurry
from operator import methodcaller

pager = "---- More ----"
prompter = "]"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read(os.path.expanduser('~/.weihu/config.ini'))
username = config.get('switch', 'username')
password = config.get('switch', 'passwd')
super_password = config.get('switch', 'super_passwd')
community_read = config.get('switch', 'community')


def telnet(ip):
    child = pexpect.spawn('telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile
    child.expect('Username:')
    child.sendline(username)
    child.expect('Password:')
    child.sendline(password)
    child.expect('>')
    child.sendline('super')
    index = child.expect(['Password:', '>'])
    if index == 0:
        child.sendline(super_password)
        child.expect('>')
        child.sendline('sys')
    else:
        child.sendline('sys')
    child.expect(']')
    return child


def close(child):
    child.sendcontrol('z')
    child.expect('>')
    child.sendline('quit')
    child.close()


def do_some(child, command):
    result = []
    child.sendline(command)
    while True:
        index = child.expect([prompter, pager], timeout=300)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(" ")
            continue
    rslt = ''.join(result).replace('\x1b[42D', '').replace(' \x1b[1D', '')
    return rslt.replace(command + '\r\n', '', 1)


def get_groups(ip):
    def _get_info(record):
        name = re_find(r'interface\s(eth-trunk)(\d+)', record, flags=re.I)
        name = ' '.join(name).lower()
        mode = re_find(r'mode\s(\S+)', record)
        if mode is None:
            mode = 'manual'
        elif 'lacp' in mode:
            mode = 'yes'
        desc = re_find(r'description\s(\S+ *\S*)', record)
        return dict(name=name, mode=mode, desc=desc)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp cu int eth-trunk')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt1 = select(r'interface', rslt.split('#'))
    rslt2 = map(_get_info, rslt1)
    return ('success', rslt2, ip)


def get_infs(ip):
    def _get_info(record):
        name = re_find(
            r'interface\s(x?gigabitethernet\S+)', record, flags=re.I)
        desc = re_find(r'description\s(\S+ *\S*)', record)
        group = re_find(r'(eth-trunk\s\d+)', record)
        return dict(name=name, desc=desc, group=group)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp cu interface')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt1 = select(r'GigabitEthernet', rslt.split('#'))
    rslt2 = map(_get_info, rslt1)
    return ('success', rslt2, ip)


def get_infs_bySnmp(ip):
    def _get_infs(oid):
        index = oid.value
        name = session.get(('ifDescr', index)).value
        desc = session.get(('ifAlias', index)).value
        if 'HUAWEI' in desc:
            desc = 'None'
        state = session.get(('ifOperStatus', index)).value
        if state == '1':
            state = 'up'
        else:
            state = 'down'
        bw = int(session.get(('ifSpeed', index)).value or 0)
        inCount = int(session.get(('ifInOctets', index)).value or 0)
        outCount = int(session.get(('ifOutOctets', index)).value or 0)
        collTime = time.time()
        return dict(
            name=name,
            desc=desc,
            state=state,
            bw=bw,
            inCount=inCount,
            outCount=outCount,
            collTime=collTime)

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
        rslt = do_some(child, 'disp int {inf}'.format(inf=inf))
        state = re_find(
            r'{inf}\scurrent\sstate\s:\s?(\w+\s?\w+)'.format(inf=inf),
            rslt).lower()
        bw = int(re_find(r'Speed\s+:\s+(\d+),', rslt))
        inTraffic = int(
            re_find(r'300 seconds input rate (\d+)\sbits/sec', rslt)) / 1000000
        outTraffic = int(
            re_find(r'300 seconds output rate (\d+)\sbits/sec',
                    rslt)) / 1000000
        infDict = dict(
            name=inf,
            state=state,
            bw=bw,
            inTraffic=inTraffic,
            outTraffic=outTraffic)
        return infDict

    try:
        child = telnet(ip)
        rslt = lmap(partial(_get_traffic, child), infs)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt, ip)


def get_vlans(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp vlan | in common')
        close(child)
        vlans = re_all(r'(\d+)\s+common +\S+', rslt)
        vlans = [int(x) for x in vlans if x != '1']
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', vlans, ip)


def get_vlans_a(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child,
                       'disp cu | in (port trunk allow|port hybrid tagged)')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    vlan_sgmt = re_all(r'(\d+) to (\d+)', rslt)
    vlans = re_all(r'(\d+)', re.sub(r'\d+ to \d+', '', rslt))
    vlan_sgmt = [(int(x[0]), int(x[1]) + 1) for x in vlan_sgmt]
    vlans = [(int(x), int(x) + 1) for x in vlans if x != '1']
    vlan_sgmt = lconcat(vlan_sgmt, vlans)
    _vlan = lambda s, e: range(s, e)
    vlans = reduce(lambda x, y: x | set(_vlan(*y)), vlan_sgmt, set())
    return ('success', list(vlans), ip)


def get_vlans_of_port(ip, port):
    try:
        child = telnet(ip)
        rslt = do_some(child, f'disp cu interface {port}')
        eth_trunk = re_find(r'eth-trunk \d+', rslt, re.I)
        rslt = do_some(child, f'disp cu interface {eth_trunk}')
        close(child)
    except Exception as e:
        raise e
    filter_str = r'^(port trunk allow|port hybrid tagged)'
    vlans = rcompose(
        methodcaller('splitlines'),
        autocurry(map)(lambda x: x.strip()),
        autocurry(filter)(lambda x: re_test(filter_str, x)))(rslt)
    rslt = reduce(lambda acc, curr: acc | _to_vlans(curr), vlans, set())
    import pprint
    pprint.pprint(rslt)


def get_ports(ip):
    def _get_info(record):
        name = re_find(r'(\S+) current state :', record)
        state = re_find(r'current state : ?(\S+ ?\S+)', record)
        desc = re_find(r'Description:(\S+ *\S+)', record)
        inTraffic = int(
            re_find(r'300 seconds input rate (\d+)\sbits/sec', record)
            or 0) / 1000000
        outTraffic = int(
            re_find(r'300 seconds output rate (\d+)\sbits/sec', record)
            or 0) / 1000000
        return dict(
            name=name,
            desc=desc,
            state=state,
            inTraffic=inTraffic,
            outTraffic=outTraffic)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp interface')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt = select(lambda x: re_test(r'^x?gigabitethernet', x, re.I),
                  re.split(r'\r\n *\r\n *', rslt))
    rslt = lmap(_get_info, rslt)
    return ('success', rslt, ip)


def get_main_card(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp device')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    temp = re_all(
        r'(?:SRU|MCU)[A-Z]\s+Present\s+PowerOn\s+Registered\s+Normal\s+(?:Master|Slave)',
        rslt)
    return ('success', len(temp), ip)


def get_power_info(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp power')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    temp = re_all(r'PWR\d\s+YES\s+DC\s+Supply', rslt)
    return ('success', len(temp), ip)


def no_shut(ip, inf):
    try:
        child = telnet(ip)
        do_some(child, 'interface {inf}'.format(inf=inf))
        do_some(child, 'undo shutdown')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', ip)
    return ('success', ip)


def get_inf(ip, inf):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'display interface {inf}'.format(inf=inf))
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    state = re_find(r'current state : (\w+\s?\w+)', rslt)
    return ('success', state, ip)


def _to_vlans(item):
    vlan_sgmt = re_all(r'(\d+) to (\d+)', item)
    vlan_sgmt = map(lambda x: range(int(x[0]), int(x[1]) + 1), vlan_sgmt)
    vlan1 = reduce(lambda acc, curr: acc | set(*curr), vlan_sgmt, set())
    vlans = re_all(r'\d+', re.sub(r'\d+ to \d+', '', item))
    vlans = map(lambda x: int(x), vlans)
    vlans = reduce(lambda acc, curr: acc.add(curr), vlans, vlan1)
    return vlans
