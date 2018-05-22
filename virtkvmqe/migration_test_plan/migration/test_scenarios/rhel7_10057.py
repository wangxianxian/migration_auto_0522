from __future__ import division
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
import os
import time
import threading
from vm import CreateTest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname
                                           (os.path.dirname
                                            (os.path.dirname
                                             (os.path.abspath(__file__))))))

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    incoming_port = str(params.get('incoming_port'))
    serial_port = int(params.get('serial_port'))
    qmp_port = int(params.get('qmp_port'))

    test = CreateTest(case_id='rhel7_10057', params=params)
    id = test.get_id()
    guest_passwd = params.get('guest_passwd')
    downtime = '30000'
    script = 'migration_dirtypage_1.c'
    query_timeout = 2400
    active_timeout = 300
    running_timeout = 300

    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('1. Start VM in src host ')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Start listening mode in dst host ')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(ip=dst_host_ip, cmd=dst_qemu_cmd,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. src guest have '
                       'programme running to generate dirty page')
    test.sub_step_log('run dirty page script')
    test.test_print('scp %s to guest' % script)
    src_guest_session.guest_cmd_output('cd /home;rm -f %s' % script)
    src_host_session.host_cmd_scp_put(local_path='%s/c_scripts/%s'
                                                 % (BASE_DIR, script),
                                      remote_path='/home/%s' % script,
                                      passwd=guest_passwd,
                                      remote_ip=src_guest_ip, timeout=300)
    chk_cmd = 'ls /home | grep -w "%s"' % script
    output = src_guest_session.guest_cmd_output(cmd=chk_cmd)
    if not output:
        test.test_error('Failed to get %s' % script)
    arch = src_guest_session.guest_cmd_output('arch')
    gcc_cmd = 'yum list installed | grep -w "gcc.%s"' % arch
    output = src_guest_session.guest_cmd_output(cmd=gcc_cmd)
    if not re.findall(r'gcc.%s' % arch, output):
        install_cmd = 'yum install -y gcc'
        install_info = src_guest_session.guest_cmd_output(install_cmd)
        if re.findall('Complete', install_info):
            test.test_print('Guest install gcc pkg successfully')
        else:
            test.test_error('Guest failed to install gcc pkg')
    compile_cmd = 'cd /home;gcc %s -o dirty1' % script
    src_guest_session.guest_cmd_output(cmd=compile_cmd)
    output = src_guest_session.guest_cmd_output('ls /home | grep -w "dirty1"')
    if not output:
        test.test_error('Failed to compile %s' % script)

    dirty_cmd = 'cd /home;./dirty1'
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(dirty_cmd, 4800))
    thread.name = 'dirty1'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    output = src_guest_session.guest_cmd_output('pgrep -x dirty1')
    if not output:
        test.test_error('Dirty1 is not running in guest')

    test.main_step_log('4. Migrate to the destination')
    cmd = '{"execute":"migrate", "arguments": {"uri": "tcp:%s:%s"}}' % \
          (dst_host_ip, incoming_port)
    src_remote_qmp.qmp_cmd_output(cmd)

    test.main_step_log('5.set downtime for migration')
    flag_active = False
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + active_timeout
    while time.time() < end_time:
        output = src_remote_qmp.qmp_cmd_output(cmd)
        if re.findall(r'"status": "active"', output):
            flag_active = True
            break
        elif re.findall(r'"status": "failed"', output):
            src_remote_qmp.qmp_cmd_output('Migration failed')
    if (flag_active == False):
        src_remote_qmp.qmp_cmd_output('Migration could not be active within %d'
                                      % active_timeout)

    downtime_cmd = '{"execute":"migrate-set-parameters",' \
                   '"arguments":{"downtime-limit": %s}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %s' % downtime, output):
        test.test_print('Set migration downtime successfully')
    else:
        test.test_error('Failed to change downtime')

    test.sub_step_log('Check the status of migration')
    flag = False
    cmd = '{"execute":"query-migrate"}'
    end_time = time.time() + query_timeout
    while time.time() < end_time:
        output = src_remote_qmp.qmp_cmd_output(cmd=cmd)
        if re.findall(r'"remaining": 0', output):
            flag = True
            break
        elif re.findall(r'"status": "failed"', output):
            src_remote_qmp.test_error('migration failed')

    if (flag == False):
        test.test_error('Migration timeout in %d' % query_timeout)

    test.main_step_log('6.Check status of guest in des host')
    cmd = '{"execute":"query-status"}'
    flag_running = False
    end_time = time.time() + running_timeout
    while time.time() < end_time:
        output = dst_remote_qmp.qmp_cmd_output(cmd=cmd, recv_timeout=3)
        if re.findall(r'"status": "running"', output):
            flag_running = True
            break

    if (flag_running == False):
        test.test_error('Dst guest is not running after migration finished %d '
                        'seconds' % running_timeout)

    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip=dst_serial.serial_login()
    external_host_ip = dst_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_serial.serial_shutdown_vm()
