from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
import re
from utils_migration import ping_pong_migration, do_migration
import threading


def scp_thread_put(session, local_path, remote_path, passwd,
                   remote_ip, timeout=600):
    session.host_cmd_scp_put(local_path, remote_path, passwd,
                         remote_ip, timeout=timeout)
    
def scp_thread_get(session, local_path, remote_path, passwd,
                   remote_ip, timeout=600):
    session.host_cmd_scp_get(local_path, remote_path, passwd,
                         remote_ip, timeout=timeout)

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    incoming_port = params.get('incoming_port')

    test = CreateTest(case_id='rhel7_10059', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Start source vm')
    src_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_guest(src_qemu_cmd, vm_alias='src')

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)

    test.main_step_log('2. Create a file in host')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host2')

    cmd = 'dd if=/dev/urandom of=/home/file_host bs=1M count=5000 oflag=direct'
    src_host_session.host_cmd_output(cmd, timeout=600)

    test.main_step_log('3. Start des vm in migration-listen mode: "-incoming tcp:0:****"')
    params.vm_base_cmd_add('incoming', 'tcp:0:%s' %incoming_port)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(ip=dst_host_ip, cmd=dst_qemu_cmd, vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('4. Transfer file from host to guest')
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    thread = threading.Thread(target=scp_thread_put,
                              args=(src_host_session,
                                    '/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    src_guest_ip, 600))

    thread.name = 'scp_thread_put'
    thread.daemon = True
    thread.start()

    test.main_step_log('5. Start migration')
    do_migration(src_remote_qmp, incoming_port, dst_host_ip)
    test.sub_step_log('Check dmesg dst guest')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        dst_serial.test_error('Guest hit call trace')
    dst_serial.serial_cmd(cmd='reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.main_step_log('6. Ping-pong migrate until file transfer finished')
    src_remote_qmp, dst_remote_qmp = ping_pong_migration(params,
                                                         id,
                                                         src_host_session,
                                                         src_remote_qmp,
                                                         dst_remote_qmp,
                                                         times=10,
                                                         query_thread='pgrep -x scp')

    test.sub_step_log('Login dst guest after ping-pong migration')
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        dst_guest_session.test_error('Guest hit call trace')

    cmd = "md5sum /home/file_host | awk '{print $1}'"
    file_src_host_md5 = src_host_session.host_cmd_output(cmd)
    cmd = "md5sum /home/file_guest | awk '{print $1}'"
    file_guest_md5 = dst_guest_session.guest_cmd_output(cmd)

    if file_src_host_md5 != file_guest_md5:
        test.test_error('Value of md5sum error!')

    test.main_step_log('7. Transfer file from guest to host')
    thread = threading.Thread(target=scp_thread_get,
                              args=(src_host_session,
                                    '/home/file_host2',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    dst_guest_ip, 600))

    thread.name = 'scp_thread_get'
    thread.daemon = True
    thread.start()

    test.main_step_log('8. Ping-Pong migration until file transfer finished.')
    ping_pong_migration(params, id, src_host_session, src_remote_qmp,
                        dst_remote_qmp, times=10, query_thread='pgrep -x scp')

    test.main_step_log('9. Check md5sum after file transfer')

    cmd = "md5sum /home/file_host | awk '{print $1}'"
    file_src_host_md5 = src_host_session.host_cmd_output(cmd)

    cmd = "md5sum /home/file_host2 | awk '{print $1}'"
    file_src_host2_md5 = src_host_session.host_cmd_output(cmd)

    if file_src_host_md5 != file_src_host2_md5:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('Login dst guest after ping-pong migration')
    dst_guest_session = GuestSession(case_id=id, params=params, ip=dst_guest_ip)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = dst_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        dst_guest_session.test_error('Guest hit call trace')

    dst_guest_session.guest_cmd_output('shutdown -h now')
    output = dst_serial.serial_output()
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')


