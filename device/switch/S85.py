#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import re
from funcy import lfilter, re_find, lmap
from funcy import re_find, re_all, update_in


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
    child.expect('Password:')
    child.sendline(super_password)
    child.expect('>')
    child.sendline('sys')
    child.expect(']')
    return child


def doSome(child, command):
    rslt = []
    child.sendline(command)
    while True:
        index = child.expect([prompter, pager], timeout=120)
        rslt.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    rslt1 = ''.join(rslt).replace(
        '\x1b[42D', '').replace(command + '\r\n', '', 1)
    return rslt1


def getInfs(ip):
    def __inf(record):
        name = re_find(r'interface\s+(X?Gigabit\S+)', record)
        desc = re_find(r'description\s+(\S+)', record)
        group = re_find(r'link-aggregation\s+(group\s+\d+)', record)
        return dict(name=name, desc=desc, group=group)

    try:
        child = telnet(ip)
        rslt = doSome(child, 'disp cu interface')
        child.sendline('quit')
        child.expect('>')
        child.sendline('quit')
        child.close()

        rslt1 = lfilter(r'X?GigabitEthernet', rslt.split('#'))
        rslt2 = lmap(__inf, rslt1)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt2, ip)


def getGroups(ip):
    try:
        child = telnet(ip)
        rslt = doSome(child, 'disp cu config | in link-aggregation')
        child.sendline('quit')
        child.expect('>')
        child.sendline('quit')
        child.close()

        temp = re_all(r'(group\s+\d+)\s+mode\s+(\w+)', rslt)
        temp1 = dict(
            re_all(r'(group\s+\d+)\s+description\s+(\S+)', rslt))
        rslt2 = [dict(isLogical='yes', name=x[0], mode=x[1], desc=temp1.get(x[0], None))
                 for x in temp]
        rslt3 = [update_in(x, ['mode'], lambda y: 'lacp' if y == 'static' else y)
                 for x in rslt2]
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt3, ip)


def main():
    pass


if __name__ == '__main__':
    main()
