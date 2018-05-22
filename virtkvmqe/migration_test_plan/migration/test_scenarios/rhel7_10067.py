import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration
import threading

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10067', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)
    iozone_url = 'http://www.iozone.org/src/current/iozone3_471.tar'
    iozone_ver = 'iozone3_471'
    downtime = '10000'
    query_migration_time = 1200

    test.main_step_log('1. Start VM with high load, with each method is ok')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('1.1 Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.sub_step_log('1.2 Running iozone in src guest')
    cmd='yum list installed | grep ^gcc.`arch`'
    output = src_guest_session.guest_cmd_output(cmd=cmd)
    if not output:
        output=src_guest_session.guest_cmd_output('yum install -y gcc')
        if not re.findall(r'Complete!', output):
            src_guest_session.test_error('gcc install Error')

    src_guest_session.guest_cmd_output('rm -rf /home/iozone*')
    src_guest_session.guest_cmd_output('cd /home;wget %s' % iozone_url)
    output = src_guest_session.guest_cmd_output('ls /home | grep %s.tar'
                                                % iozone_ver)
    if not output:
        test.test_error('Failed to get iozone file')
    time.sleep(10)
    src_guest_session.guest_cmd_output('cd /home; tar -xvf %s.tar'
                                       % iozone_ver)
    arch = src_guest_session.guest_cmd_output('arch')
    if re.findall(r'ppc64le', arch):
        cmd = 'cd /home/%s/src/current/;make linux-powerpc64' % iozone_ver
        src_guest_session.guest_cmd_output(cmd=cmd)
    elif re.findall(r'x86_64', arch):
        cmd = 'cd /home/%s/src/current/;make linux-AMD64' % iozone_ver
        src_guest_session.guest_cmd_output(cmd=cmd)
    elif re.findall(r'S390X', arch):
        cmd = 'cd /home/%s/src/current/;make linux-S390X' % iozone_ver
        src_guest_session.guest_cmd_output(cmd=cmd)
    time.sleep(5)
    iozone_cmd = 'cd /home/%s/src/current/;./iozone -a' % iozone_ver
    thread = threading.Thread(target=src_guest_session.guest_cmd_output,
                              args=(iozone_cmd,1200))
    thread.name = 'iozone'
    thread.daemon = True
    thread.start()
    time.sleep(10)
    pid =src_guest_session.guest_cmd_output('pgrep -x iozone')
    if pid:
        src_guest_session.test_print('iozone is running in guest')
    else:
        src_guest_session.test_error('iozone is not running in guest')

    test.main_step_log('2. Start listening mode')
    incoming_val = 'tcp:0:%s' % incoming_port
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. Set a reasonable downtime value for migration')
    downtime_cmd = '{"execute":"migrate-set-parameters","arguments":' \
                   '{"downtime-limit": %s}}' % downtime
    src_remote_qmp.qmp_cmd_output(cmd=downtime_cmd)
    paras_chk_cmd = '{"execute":"query-migrate-parameters"}'
    output = src_remote_qmp.qmp_cmd_output(cmd=paras_chk_cmd)
    if re.findall(r'"downtime-limit": %s' % downtime, output):
        test.test_print('Change downtime successfully')
    else:
        test.test_error('Failed to change downtime')

    test.main_step_log('4.Do live migration')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip,
                              chk_timeout_2=query_migration_time)
    if (check_info == False):
        test.test_error('Migration timeout after changing downtime')

    test.main_step_log('5. Check the status of guest on dst host')
    test.sub_step_log('5.1. Reboot guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('5.2 Ping external host')
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    dst_guest_session.guest_ping_test('www.redhat.com', 10)

    test.sub_step_log('5.3 DD a file inside guest')
    cmd_dd = 'dd if=/dev/zero of=file1 bs=1M count=100 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        test.test_error('Failed to dd a file in guest')

    test.sub_step_log('5.4 Shutdown guest successfully')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')