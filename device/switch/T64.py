#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import re
import os
from functools import reduce
from toolz import thread_last
from funcy import distinct, re_find, rcompose, partial, map, lmap
from funcy import re_all, re_test, select

pager = "--More--"
prompter = "#"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read(os.path.expanduser('~/.weihu/config.ini'))
username = config.get('switch', 'username')
password = config.get('switch', 'passwd')
super_password = config.get('switch', 'super_passwd')


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
    child.expect(prompter)
    child.sendline('exit')
    child.close()


def get_groups(ip):
    def _get_desc(child, group):
        name = group['name']
        rslt = do_some(child, 'show run interface {name}'.format(name=name))
        desc = re_find(r'description\s(\S+ *\S*)', rslt)
        group['desc'] = desc
        if group['mode'] == 'active':
            group['mode'] = 'yes'
        return group

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show run | in smartgroup [0-9]+')
        ff = rcompose(partial(map, lambda x: x.strip()),
                      distinct,
                      partial(map, r'(smartgroup\s\d+)\smode\s(\w+)'),
                      partial(map, lambda x: dict(name=x[0].replace(' ', ''), mode=x[1])))
        temp = ff(rslt.splitlines()[:-1])
        get_desc = partial(_get_desc, child)
        groups = lmap(get_desc, temp)
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
        if group:
            group = group.replace(' ', '')
        inf['desc'] = desc
        inf['group'] = group
        return inf

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show run | in interface (xg|g|f)ei_')
        temp = [dict(name=x) for x in re_all('interface\s(\S+)', rslt)]
        get_desc = partial(_get_desc, child)
        infs = lmap(get_desc, temp)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', infs, ip)


def get_traffics(ip, infs):
    def _get_traffic(child, inf):
        rslt = do_some(child, 'show interface {inf}'.format(inf=inf))
        state = re_find(r'{inf}\sis\s(\w+\s?\w+)'.format(inf=inf),
                        rslt).lower()
        bw = int(re_find(r'BW\s(\d+)\sKbits', rslt)) / 1000
        inTraffic = int(re_find(r'120 seconds input.*:\s+(\d+)\sBps', rslt)) * 8 / 1000000
        outTraffic = int(re_find(r'120 seconds output.*:\s+(\d+)\sBps', rslt)) * 8 / 1000000
        infDict = dict(name=inf, state=state, bw=bw, inTraffic=inTraffic, outTraffic=outTraffic)
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
        name = re_find(r'^((?:xg|g|f)ei\S+) is \w+ ?\w+,', record)
        state = re_find(r'^(?:xg|g|f)ei\S+ is (\w+ ?\w+),', record)
        desc = re_find(r'Description is (\S+ *\S+)', record)
        inTraffic = int(re_find(r'120 seconds input.*:\s+(\d+)\sBps', record) or 0) * 8 / 1000000
        outTraffic = int(re_find(r'120 seconds output.*:\s+(\d+)\sBps', record) or 0) * 8 / 1000000
        return dict(name=name, desc=desc, state=state, inTraffic=inTraffic, outTraffic=outTraffic)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'show interface')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt = thread_last(rslt,
                       (re.split, r'\r\r\n *\r\r\n *'),
                       (select, r'^(?:xg|g|f)ei_'),
                       (lmap, _get_info))
    return ('success', rslt, ip)


def main():
    pass


if __name__ == '__main__':
    main()
