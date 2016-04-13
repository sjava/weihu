#!/usr/bin/env python
# -*- coding: utf-8 -*-
import pexpect
import configparser
import sys
import os
from funcy import re_find, select, map, compose, partial, lmapcat
from funcy import lmap, re_all, join_with, identity, count_by

prompter = "]"
pager = "---- More ----"
logfile = sys.stdout

conf = configparser.ConfigParser()
conf.read(os.path.expanduser('~/.weihu/config.ini'))
username = conf.get('bras', 'username')
password = conf.get('bras', 'password')


def telnet(ip):
    child = pexpect.spawn('telnet {ip}'.format(ip=ip),
                          encoding='ISO-8859-1')
    child.logfile = logfile
    child.expect('Username:')
    child.sendline(username)
    child.expect('Password:')
    child.sendline(password)
    child.expect('>')
    child.sendline('sys')
    child.expect(prompter)
    return child


def close(child):
    child.sendcontrol('z')
    child.expect('>')
    child.sendline('q')
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
    return ''.join(rslt).replace('\x1b[42D', '').replace(cmd + '\r\n', '', 1)


def get_bingfa(ip):
    def _get_users(child, slot):
        record = do_some(
            child, 'disp max-online slot {s}'.format(s=slot))
        users = re_find(
            r'Max online users since startup\s+:\s+(\d+)', record)
        users = int(users or 0)
        date = re_find(
            r'Time of max online users\s+:\s+(\d{4}-\d{2}-\d{2})', record)
        return (slot, users, date)

    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp dev | in BSU')
        ff = compose(partial(select, bool),
                     partial(map, r'(\d+)\s+BSU'))
        slots = ff(rslt.split('\r\n'))
        maxUsers = lmap(partial(_get_users, child), slots)
        close(child)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', maxUsers, ip)


def get_vlan_users(ip, inf):
    def _get_users(child, i):
        rslt = do_some(child, 'disp access-user interface {i} | in /'.format(i=i))
        users = re_all(r'(\d+)/', rslt)
        return users

    try:
        child = telnet(ip)
        infs = do_some(child, 'disp cu interface | in Eth-Trunk{inf}\.'.format(inf=inf))
        infs = re_all(r'interface (\S+)', infs)
        rslt = lmapcat(partial(_get_users, child), infs)
        close(child)
        rslt = count_by(int, rslt)
    except (pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', rslt, ip)


def get_ip_pool(ip):
    def _get_sections(child, name):
        rslt = do_some(child, 'disp cu configuration ip-pool {name}'.format(name=name))
        sections = re_all(r'section \d+ (\S+) (\S+)', rslt)
        return sections
    try:
        child = telnet(ip)
        rslt = do_some(child, 'disp domain 163.js | in pool-name')
        poolNames = re_all(r'pool-name\s+:\s(\S+)', rslt)
        ips = lmapcat(partial(_get_sections, child), poolNames)
        close(child)
    except(pexpect.EOF, pexpect.TIMEOUT) as e:
        return ('fail', None, ip)
    return ('success', ips, ip)
