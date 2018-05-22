from __future__ import division
import os
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
import time
import threading
from vm import CreateTest
from utils_migration import do_migration

BASE_DIR = os.path.dirname(os.path.dirname
                           (os.path.dirname
                            (os.path.dirname
                             (os.path.dirname(os.path.abspath(__file__))))))

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10044', params=params)
    id = test.get_id()
    guest_passwd = params.get('guest_passwd')
    src_host_session = HostSession(id, params)
    downtime = 10000
    gap_downtime = 5000
    script = 'migration_dirtypage_2.c'

    test.main_step_log('1. guest with heavy memory load with either of '
                       'the following methods')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.2 Run some program to generate dirty page')
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
        install_cmd = 'yum install -y ^gcc.`arch`'
        install_info = src_guest_session.guest_cmd_output(install_cmd)
        if re.findall('Complete', install_info):
            test.test_print('Guest install gcc pkg successfully')
        else:
            test.test_error('Guest failed to install gcc pkg')
    compile_cmd = 'cd /home;gcc %s -o dirty2' % script
    src_guest_session.guest_cmd_output(cmd=compile_cmd)
    output = src_guest_session.guest_cmd_output('ls /home | grep -w "dirty2"')
    if not output:
        test.test_error('Failed to compile %s' % script)

    dirty_cmd = 'cd /home;./dirty2'
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(dirty_cmd, 4800))
    thread.name = 'dirty2'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    output = src_guest_session.guest_cmd_output('pgrep -x dirty2')
    if not output:
        test.test_error('Dirty2 is not running in guest')

    test.main_step_log('2. Start listening mode on dst host')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Set a reasonable migrate downtime')
    downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                '{"downtime-limit": %d}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %d' % downtime, output):
        test.test_print('Set migration downtime successfully')
    else:
        test.test_error('Failed to change downtime')

    test.main_step_log('4. Do live migration.')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.main_step_log('5. when the "Migration status" is "completed", '
                       'check the "downtime" value')
    output = eval(src_remote_qmp.qmp_cmd_output('{"execute":"query-migrate"}'))
    real_downtime = int(output.get('return').get('downtime'))
    src_remote_qmp.test_print('The real downtime is: %d' % real_downtime)
    gap_cal = real_downtime-downtime
    if (gap_cal > gap_downtime):
        test.test_error('The real downtime value is much more than the value '
                        'that you set by %s milliseconds' % gap_downtime)
    else:
        test.test_print('The real downtime value is not much more than '
                        'the value that you set')

    test.main_step_log('6 Check the status of guest')
    test.sub_step_log('6.1. Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('6.2 Ping external host')
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    dst_guest_session.guest_ping_test('www.redhat.com', 10)

    test.sub_step_log('6.3 Shutdown guest successfully')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')
