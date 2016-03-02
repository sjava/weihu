#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import re
from functools import reduce
from funcy import filter, re_find, map, lmap, partial, select
from funcy import select_values, re_all, update_in, re_test

pager = "---- More ----"
prompter = "]"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read('config.ini')
username = config.get('switch', 'username')
password = config.get('switch', 'passwd')
super_password = config.get('switch', 'super_passwd')


def telnet(ip):
    child = pexpect.spawn('telnet {0}'.format(ip), encoding='ISO-8859-1')
    child.logfile = logfile

    child.expect('Username:')
    child.sendline(username)
    child.expect('Password:')
    child.sendline(password)
    child.expect('>')
    child.sendline('super')
    child.expect('Password:')
    child.sendline(super_password)
    child.expect('>')
    child.sendline('sys')
    child.expect(']')
    return child


def close(child):
    child.sendcontrol('z')
    child.expect('>')
    child.sendline('quit')
    child.close()


def do_some(child, cmd):
    rslt = []
    child.sendline(cmd)
    while True:
        index = child.expect([prompter, pager], timeout=120)
        rslt.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt1 = ''.join(rslt).replace('\x1b[42D', '')\
                         .replace(cmd + '\r\n', '', 1)
    return rslt1


def get_infs(ip):
    def _inf(record):
        name = re_find(r'interface\s+(X?Gigabit\S+)', record)
        desc = re_find(r'description\s+(\S+ *\S*)', record)
        group = re_find(r'link-aggregation\s+(group\s+\d+)', record)
        return dict(name=name, desc=desc, group=group)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp cu interface')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt1 = filter(r'X?GigabitEthernet', rslt.split('#'))
    rslt2 = map(_inf, rslt1)
    return ('success', rslt2, ip)


def get_groups(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp cu config | in link-aggregation')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    temp = re_all(r'(group\s+\d+)\s+mode\s+(\w+)', rslt)
    temp1 = dict(re_all(r'(group\s+\d+)\s+description\s+(\S+ *\S*)', rslt))
    rslt1 = [dict(name=x[0],
                  mode=x[1],
                  desc=temp1.get(x[0], None)) for x in temp]
    rslt3 = [update_in(x, ['mode'], lambda y: 'lacp' if y == 'static' else y)
             for x in rslt1]
    return ('success', rslt3, ip)


def get_traffics(ip, infs):
    def _get_traffic(child, inf):
        rslt = do_some(child, 'disp int {inf}'.format(inf=inf))
        state = re_find(r'{inf}\scurrent\sstate\s:\s?(\w+\s?\w+)'
                        .format(inf=inf), rslt).lower()
        bw = re_find(r'(\d+[MG])bps-speed mode', rslt)
        if bw is None:
            bw = 0
        elif 'M' in bw:
            bw = int(bw.replace('M', ''))
        else:
            bw = int(bw.replace('G', '')) * 1000
        inTraffic = int(re_find(r'\d+ seconds input:\s+\d+\spackets/sec\s(\d+)\sbits/sec', rslt)) / 1000000
        outTraffic = int(re_find(r'\d+ seconds output:\s+\d+\spackets/sec\s(\d+)\sbits/sec', rslt)) / 1000000
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
    def _vlan(record):
        if re_test(r'(Ports:\snone.*Ports:\snone)', record, re.S):
            return 0
        vlan = re_find(r'VLAN\sID:\s(\d+)', record)
        vlan = int(vlan or 0)
        return vlan

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp vlan all')
        close(child)
        rslt = re.split(r'\r\n *\r\n', rslt)
        vlans = select(lambda x: x > 1,
                       lmap(_vlan, rslt))
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', vlans, ip)


def get_ports(ip):
    def _get_info(record):
        name = re_find(r'(\S+) current state :', record)
        state = re_find(r'current state : ?(\S+ ?\S+)', record)
        desc = re_find(r'Description: (\S+ *\S+)', record)
        inTraffic = int(re_find(r'\d+ seconds input:\s+\d+\spackets/sec\s(\d+)\sbits/sec', record) or 0) / 1000000
        outTraffic = int(re_find(r'\d+ seconds output:\s+\d+\spackets/sec\s(\d+)\sbits/sec', record) or 0) / 1000000
        return dict(name=name, desc=desc, state=state, inTraffic=inTraffic, outTraffic=outTraffic)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp interface')
        close(child)
        rslt = re.split(r'\r\n *\r\n', rslt)
        rslt = select(lambda x: bool(x['name']),
                      lmap(_get_info, rslt))
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt, ip)


def main():
    pass


if __name__ == '__main__':
    main()
