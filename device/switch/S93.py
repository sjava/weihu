#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import re
from funcy import lmap, map, re_find
from funcy import select, partial

pager = "---- More ----"
prompter = "]"
logfile = sys.stdout

config = configparser.ConfigParser()
config.read('config.ini')
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
        index = child.expect([prompter, pager], timeout=120)
        result.append(child.before)
        if index == 0:
            break
        else:
            child.send(" ")
            continue
    rslt = ''.join(result).replace('\x1b[42D', '')
    return rslt.replace(command + '\r\n', '', 1)


def get_groups(ip):
    def _get_info(record):
        name = re_find(r'interface\s(eth-trunk)(\d+)', record, flags=re.I)
        name = ' '.join(name).lower()
        mode = re_find(r'mode\s(\S+)', record)
        if mode is None:
            mode = 'manual'
        desc = re_find(r'description\s(\S+)', record)
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
        name = re_find(r'interface\s(x?gigabitethernet\S+)', record, flags=re.I)
        desc = re_find(r'description\s(\S+)', record)
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


def get_traffics(ip, infs):
    def _get_traffic(child, inf):
        rslt = do_some(child, 'disp int {inf}'.format(inf=inf))
        state = re_find(r'{inf}\scurrent\sstate\s:\s?(\w+\s?\w+)'
                        .format(inf=inf), rslt).lower()
        bw = int(re_find(r'Speed\s+:\s+(\d+),', rslt))
        inTraffic = int(re_find(r'300 seconds input rate (\d+)\sbits/sec', rslt)) / 1000000
        outTraffic = int(re_find(r'300 seconds output rate (\d+)\sbits/sec', rslt)) / 1000000
        infDict = dict(name=inf, state=state, bw=bw, inTraffic=inTraffic, outTraffic=outTraffic)
        return infDict

    try:
        child = telnet(ip)
        rslt = lmap(partial(_get_traffic, child), infs)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt, ip)


def main():
    pass


if __name__ == '__main__':
    main()
