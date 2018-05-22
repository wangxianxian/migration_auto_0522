import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import query_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = src_host_ip
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    share_images_dir = params.get('share_images_dir')
    test = CreateTest(case_id='rhel7_10022', params=params)
    id = test.get_id()
    guest_name = test.guest_name

    test.main_step_log('1. Boot a guest.')
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('Check the status of src guest')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(case_id=id, params=params,
                                     ip=src_host_ip, port=serial_port)
    src_guest_ip = src_serial.serial_login()
    guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Save VM state into a compressed file in host')
    src_remote_qmp.qmp_cmd_output('{"execute":"stop"}')
    src_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    src_remote_qmp.qmp_cmd_output('{"execute":"migrate_set_speed", '
                                  '"arguments": { "value": 104857600 }}')

    statefile = '/%s/STATEFILE.gz' % share_images_dir
    src_host_session.host_cmd(cmd=('rm -rf %s' % statefile))
    src_remote_qmp.qmp_cmd_output('{"execute":"migrate",'
                                  '"arguments":{"uri": "exec:gzip -c > %s"}}'
                                  % statefile, recv_timeout=5)

    test.sub_step_log('Check the status of migration')
    info = query_migration(src_remote_qmp)
    if (info == True):
        test.test_print('Migration succeed')
    if (info == False):
        test.test_error('Migration timeout')

    src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    time.sleep(3)
    src_chk_cmd = 'ps -aux | grep %s | grep -vE grep' % guest_name
    output = src_host_session.host_cmd_output(cmd=src_chk_cmd,
                                              echo_cmd=False,
                                              verbose=False)
    if output:
        src_pid = re.split(r"\s+", output)[1]
        src_host_session.host_cmd_output('kill -9 %s' % src_pid,
                                         echo_cmd=False)

    test.main_step_log('3. Load the file in dest host(src host).')
    params.vm_base_cmd_add('incoming', '"exec: gzip -c -d %s"' % statefile)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=dst_qemu_cmd, vm_alias='dst')

    test.sub_step_log('3.1 Login dst guest')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    while True:
        output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
        if re.findall(r'"paused"', output):
            break
        time.sleep(3)

    dst_remote_qmp.qmp_cmd_output('{"execute":"cont"}')
    dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')

    dst_serial = RemoteSerialMonitor(case_id=id, params=params,
                                     ip=src_host_ip, port=serial_port)
    guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.main_step_log('4. Check if guest works well.')
    test.sub_step_log('4.1 Guest mouse and keyboard.')
    test.sub_step_log('4.2. Ping external host / copy file between guest and host')
    guest_session.guest_ping_test('www.redhat.com', 10)

    test.sub_step_log('4.3 dd a file inside guest.')
    cmd_dd = 'dd if=/dev/zero of=/tmp/dd.io bs=512b count=2000 oflag=direct'
    guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)

    test.sub_step_log('check dmesg info')
    cmd = 'dmesg'
    output = guest_session.guest_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        guest_session.test_error('Guest hit call trace')

    test.sub_step_log('4.4. Reboot and then shutdown guest.')
    dst_serial.serial_cmd(cmd='reboot')
    dst_serial.serial_login()
    dst_serial.serial_shutdown_vm()