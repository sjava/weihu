#!/usr/bin/env python
# -*- coding: utf-8 -*-
import configparser
import pexpect
import sys
import os
import re
from funcy import re_find, select, distinct, re_all
from funcy import lmapcat, partial, count_by

prompter = "#"
pager = "--More--"
logfile = sys.stdout

conf = configparser.ConfigParser()
conf.read(os.path.expanduser('~/.weihu/config.ini'))
username = conf.get('bras', 'm6k_user')
password = conf.get('bras', 'm6k_pass')
super_pass = conf.get('bras', 'm6k_super')


def telnet(ip):
    child = pexpect.spawn('telnet {ip}'.format(ip=ip), encoding='ISO-8859-1')
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
    rslt2 = [
        re_find(
            r'Slot:(\d+).*Total\s+(\d+)\s+(\d{4}/\d{2}/\d{2})', x, flags=re.S)
        for x in rslt1
    ]
    rslt3 = select(bool, rslt2)
    rslt3 = [(x[0], int(x[1]), x[2]) for x in rslt3]
    return ('success', rslt3, ip)


def get_vlan_users(ip, inf):
    def _get_users(child, i):
        rslt = do_some(
            child,
            'show subscriber interface {i} | in external-vlan'.format(i=i))
        vlans = re_all(r'external-vlan\s+:(\d+)', rslt)
        return vlans

    try:
        child = telnet(ip)
        rslt = do_some(
            child,
            'show running-config | in smartgroup{inf}\.'.format(inf=inf))
        infs = distinct(re_all(r'(smartgroup\S+)', rslt))
        vlans = lmapcat(partial(_get_users, child), infs)
        close(child)
        vlans = count_by(int, vlans)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', vlans, ip)


def get_itv_online(ip):
    try:
        child = telnet(ip)
        rslt = do_some(child, 'show subscriber statistics domain vod')
        count = re_find(r'all-stack\s*:\s+(\d+)', rslt, flags=re.I)
        count = int(count) if count else 0
        rslt = do_some(child, 'show subscriber statistics domain itv')
        count1 = re_find(r'all-stack\s*:\s+(\d+)', rslt, flags=re.I)
        count1 = int(count1) if count1 else 0
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT):
        return ('fail', None, ip)
    return ('success', count + count1, ip)
