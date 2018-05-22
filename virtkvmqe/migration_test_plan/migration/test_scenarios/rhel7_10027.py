import re
from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
from utils_migration import do_migration
import time


def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    guest_passwd = params.get('guest_passwd')
    incoming_port = params.get('incoming_port')

    test = CreateTest(case_id='rhel7_10027', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. start vm on src host with \"-S\" in qemu cli')
    params.vm_base_cmd_add('S', 'None')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    test.sub_step_log('Check the status of src guest')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.main_step_log('2. start listening mode on the dst host '
                       'with \"-incoming tcp:0:5800\" '
                       'but without \"-S\" in qemu cli')
    params.vm_base_cmd_add('incoming', 'tcp:0:%s' % incoming_port)
    params.vm_base_cmd_del('S', 'None')
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(ip=dst_host_ip,
                                       cmd=dst_qemu_cmd, vm_alias='dst')
    test.sub_step_log('Check the status of dst guest')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('3. "cont" gust, after kernel start to load, '
                       'implement migration during vm boot ')
    src_remote_qmp.qmp_cmd_output('{ "execute": "cont" }')
    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(case_id=id, params=params,
                                     ip=src_host_ip, port=serial_port)

    search_str = '[    0.000000]'
    while 1:
        output = src_serial.serial_output(max_recv_data=128, search_str=search_str)
        if re.findall(r'Found the searched keyword', output):
            test.test_print(output)
            do_migration(src_remote_qmp, incoming_port, dst_host_ip)
            break
        else:
            test.test_print(output)
        if re.findall(r'login:', output):
            test.test_error('Failed to find the keyword: %s' % search_str)

    test.main_step_log('4. After finish migration and guest boot up, '
                       'check if guest works well')

    dst_serial = RemoteSerialMonitor(case_id=id, params=params,
                                     ip=dst_host_ip, port=serial_port)

    timeout = 600
    endtime = time.time() + timeout
    bootup = False
    while time.time() < endtime:
        cmd = 'root'
        dst_serial.send_cmd(cmd)
        output = dst_serial.rec_data(recv_timeout=8)
        dst_serial.test_print(info=output, serial_debug=True)
        if re.findall(r'Password', output):
            dst_serial.send_cmd(guest_passwd)
            dst_serial.test_print(guest_passwd, serial_debug=True)
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

                dst_serial.send_cmd(guest_passwd)
                dst_serial.test_print(guest_passwd, serial_debug=True)
                output = dst_serial.rec_data(recv_timeout=10)
                dst_serial.test_print(info=output, serial_debug=True)
                if re.search(r"login:", output):
                    bootup = True
                    break
    if bootup == False:
        test.test_error('Guest boot up failed under %s sec' % timeout)

    test.sub_step_log('4.1 Guest mouse and keyboard.')
    test.sub_step_log('4.2. Reboot guest')
    test.sub_step_log('check dmesg info')
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
        test.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('4.3 Ping external host ')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('4.4 dd a file inside guest.')
    cmd_dd = 'dd if=/dev/zero of=/home/file1 bs=1M count=500 oflag=direct'
    output = dst_guest_session.guest_cmd_output(cmd=cmd_dd, timeout=600)
    if not output or re.findall('error', output):
        test.test_error('Failed to dd a file in guest')

    test.sub_step_log('4.5. Shutdown guest.')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')