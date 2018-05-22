import time
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import query_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')
    test = CreateTest(case_id='rhel7_10068', params=params)
    id = test.get_id()
    guest_pwd = params.get('guest_passwd')

    test.main_step_log('1.Start VM in src host')
    params.vm_base_cmd_add('S', 'None')
    params.vm_base_cmd_add('monitor','tcp:0:5555,server,nowait')

    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')

    test.sub_step_log('Check the status of src guest')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.main_step_log('2. Start listening mode in dst host ')
    params.vm_base_cmd_del('S','None')
    params.vm_base_cmd_del('monitor','tcp:0:5555,server,nowait')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip, 
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)

    test.main_step_log('3. Start live migration with '
                       'running below script on src host')
    cmd='echo c | nc localhost 5555; sleep 0.6; ' \
        'echo migrate tcp:%s:%s | nc localhost 5555' % \
        (dst_host_ip, incoming_port)
    src_host_session.host_cmd(cmd=cmd)
    
    test.main_step_log('4.Check guest on des, guest should work well')
    migration_flag = query_migration(src_remote_qmp)
    if (migration_flag == False):
        src_remote_qmp.test_error('migration timeout')
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-status"}')
    if not re.findall(r'"status": "running"', output):
            dst_remote_qmp.test_error('migration status error')

    test.main_step_log('5.Reboot guest, guest should work well.')
    timeout = 600
    endtime = time.time() + timeout
    bootup = False
    while time.time() < endtime:
        cmd = 'root'
        dst_serial.send_cmd(cmd)
        output = dst_serial.rec_data(recv_timeout=8)
        dst_serial.test_print(info=output, serial_debug=True)
        if re.findall(r'Password', output):
            dst_serial.send_cmd(guest_pwd)
            dst_serial.test_print(guest_pwd, serial_debug=True)
            output = dst_serial.rec_data(recv_timeout=8)
            dst_serial.test_print(info=output, serial_debug=True)
            if re.search(r"login:", output):
                bootup = True
                break
            if re.findall(r'Login incorrect', output):
                dst_serial.test_print(info='Try to login again.')
                cmd = 'root'
                dst_serial.send_cmd(cmd)
                output = dst_serial.rec_data(recv_timeout=10)
                dst_serial.test_print(info=output, serial_debug=True)

                dst_serial.send_cmd(guest_pwd)
                dst_serial.test_print(guest_pwd, serial_debug=True)
                output = dst_serial.rec_data(recv_timeout=10)
                dst_serial.test_print(info=output, serial_debug=True)
                if re.search(r"login:", output):
                    bootup = True
                    break
    if bootup == False:
        test.test_error('Guest boot up failed under %s sec' % timeout)

    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip=dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)
    dst_guest_session.guest_ping_test(dst_ip='www.redhat.com', count=10)

    test.sub_step_log('quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_serial.serial_shutdown_vm()
