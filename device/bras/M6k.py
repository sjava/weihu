#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import re
from funcy import re_find, select

prompter = "#"
pager = "--More--"
logfile = sys.stdout

conf = configparser.ConfigParser()
conf.read('config.ini')
username = conf.get('bras', 'm6k_user')
password = conf.get('bras', 'm6k_pass')
super_pass = conf.get('bras', 'm6k_super')


def telnet(ip):
    child = pexpect.spawn('telnet {ip}'.format(ip=ip),
                          encoding='ISO-8859-1')
    child.logfile = logfile
    child.expect('Username:')
    child.sendline(username)
    child.expect('Password:')
    child.sendline(password)
    child.expect('>')
    child.sendline('enable')
    child.expect('Password:')
    child.sendline(super_pass)
    child.expect(prompter)
    return child


def close(child):
    child.sendcontrol('z')
    child.expect(prompter)
    child.sendline('exit')
    child.close()


def do_some(child, cmd):
    child.sendline(cmd)
    rslt = []
    while True:
        index = child.expect([prompter, pager], timeout=120)
        rslt.append(child.before)
        if index == 0:
            break
        else:
            child.send(' ')
            continue
    return ''.join(rslt).replace('\x08', '').replace(cmd + '\r\n', '', 1)


def get_bingfa(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'show subscriber peak')
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    rslt1 = [x for x in re.split(r'\r\n-+\r\n', rslt) if 'Slot:' in x]
    rslt2 = [re_find(
        r'Slot:(\d+).*Total\s+(\d+)\s+(\d{4}/\d{2}/\d{2})', x, flags=re.S) for x in rslt1]
    rslt3 = select(bool, rslt2)
    rslt3 = [(x[0], int(x[1]), x[2]) for x in rslt3]
    return ('success', rslt3, ip)
