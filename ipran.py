#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
from multiprocess import Pool, Manager
from device.ipran import A
from funcy import partial

processor = 32
devicesFile = 'ipran/a.csv'
logFile = 'result/ipran_log.csv'
rsltFile = 'result/ipran_info.csv'


def clear_log():
    for f in (logFile, rsltFile):
        if os.path.exists(f):
            os.remove(f)
        os.mknod(f)


def _inf_ospf_check(lock, ip):
    mark, rslt, ip = A.infs_ospf_check(ip)
    with lock:
        with open(logFile, 'a') as lf:
            lf.write('{ip}:{mark}\r\n'.format(ip=ip, mark=mark))
        if mark == 'success' and rslt:
            with open(rsltFile, 'a') as rf:
                for inf in rslt:
                    rf.write('{ip}:{inf}\r\n'.format(ip=ip, inf=inf))


def ospf_check():
    clear_log()
    devices = [x.split(',')[0]
               for x in open(devicesFile)]
    pool = Pool(processor)
    lock = Manager().Lock()
    list(pool.map(partial(_inf_ospf_check, lock), devices))
    pool.close()
    pool.join()


def main():
    ospf_check()

if __name__ == '__main__':
    main()
