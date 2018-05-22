from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
from vm import CreateTest
from utils_migration import do_migration
import re
import time
import threading

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    incoming_port = params.get('incoming_port')
    serial_port = int(params.get('serial_port'))
    qmp_port = int(params.get('qmp_port'))

    test = CreateTest(case_id='rhel7_10062', params=params)
    id = test.get_id()
    query_migration_time = 2400
    src_host_session = HostSession(id, params)
    src_qemu_cmd = params.create_qemu_cmd()

    test.main_step_log('Scenario 1:src: vhost des'
                       'fileCopy: from src host to guest ')
    test.main_step_log('1.1 Start VM in src host ')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.main_step_log('1.2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev','tap,id=tap0,vhost=on')
    params.vm_base_cmd_add('netdev','tap,id=tap0')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('1.3.Copy a large file(eg 2G) from host to guest '
                       'in src host, then start to do migration '
                       'during transferring file.')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host')
    cmd = 'dd if=/dev/urandom of=/home/file_host bs=1M count=2048 oflag=direct'
    src_host_session.host_cmd_output(cmd, timeout=600)
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_put,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    src_guest_ip, 600))
    thread.name = 'scp_thread_put'
    thread.daemon = True
    thread.start()
    time.sleep(3)

    test.main_step_log('1.4. Migrate to the destination')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip,
                              chk_timeout_2=query_migration_time)
    if (check_info == False):
        test.test_error('Migration timeout ')

    test.main_step_log('1.5.After migration finishes,until transferring finished'
                        'reboot guest,Check file in host and guest.'
                        'value of md5sum is the same.')
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break
    time.sleep(3)

    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id,params=params,ip=dst_guest_ip)

    test.sub_step_log('network of guest should be woking')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('1.6 quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_serial.serial_shutdown_vm()
    src_host_session.check_guest_process(src_ip=src_host_ip,
                                         dst_ip=dst_host_ip)

    time.sleep(3)
    test.main_step_log('Scenario 2.src: des: vhost,'
                       'fileCopy: from src host to guest')
    src_host_session = HostSession(id, params)

    test.main_step_log('2.1. Start VM in src host ')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_del('incoming', incoming_val)
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.main_step_log('2.2 Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev', 'tap,id=tap0')
    params.vm_base_cmd_add('netdev', 'tap,id=tap0,vhost=on')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('2.3.Copy a large file(eg 2G) from host to guest '
                       'in src host, then start to do migration '
                       'during transferring file.')
    src_host_session.host_cmd(cmd='rm -rf /home/file_host')
    cmd = 'dd if=/dev/urandom of=/home/file_host bs=1M count=2000 oflag=direct'
    src_host_session.host_cmd_output(cmd, timeout=600)
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_put,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    src_guest_ip, 600))
    thread.name = 'scp_thread_put'
    thread.daemon = True
    thread.start()
    time.sleep(3)

    test.main_step_log('2.4. Migrate to the destination')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip,
                              chk_timeout_2=query_migration_time)
    if (check_info == False):
        test.test_error('Migration timeout ')

    test.main_step_log('2.5.After migration finishes,until transferring finished'
                       'reboot guest,Check file in host and guest.'
                       'value of md5sum is the same.')
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break

    time.sleep(3)

    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)

    test.sub_step_log('network of guest should be woking')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('2.6.quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_serial.serial_shutdown_vm()
    src_host_session.check_guest_process(src_ip=src_host_ip,
                                         dst_ip=dst_host_ip)

    time.sleep(3)
    test.main_step_log('Scenario 3.src:vhost des:,'
                       'fileCopy: from src guest to host')
    src_host_session = HostSession(id, params)

    test.main_step_log('3.1. Start VM in src host ')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_del('incoming', incoming_val)
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.main_step_log('3.2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev','tap,id=tap0,vhost=on')
    params.vm_base_cmd_add('netdev','tap,id=tap0')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('3.3.Copy a large file(eg 2G) from host to guest '
                       'in src host, then start to do migration '
                       'during transferring file. ')
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    cmd = 'dd if=/dev/urandom of=/home/file_guest ' \
          'bs=1M count=2000 oflag=direct'
    src_guest_session.guest_cmd_output(cmd, timeout=600)
    src_host_session.host_cmd_output(cmd='rm -rf /home/file_host')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_get,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    src_guest_ip, 600))
    thread.name = 'scp_thread_get'
    thread.daemon = True
    thread.start()
    time.sleep(3)

    test.main_step_log('3.4. Migrate to the destination')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip,
                              chk_timeout_2=query_migration_time)
    if (check_info == False):
        test.test_error('Migration timeout ')

    test.main_step_log('3.5.After migration finishes,until transferring finished'
                        'reboot guest,Check file in host and guest.'
                        'value of md5sum is the same.')
    test.sub_step_log('check status of transferring the file')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break

    time.sleep(3)
    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id,params=params,ip=dst_guest_ip)

    test.sub_step_log('network of guest should be woking')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('3.6 quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_serial.serial_shutdown_vm()
    src_host_session.check_guest_process(src_ip=src_host_ip,
                                         dst_ip=dst_host_ip)

    time.sleep(3)
    test.main_step_log('Scenario 4.src: des:vhost ,'
                       'fileCopy: from src guest to host')
    src_host_session = HostSession(id, params)

    test.main_step_log('4.1. Start VM in src host ')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_del('incoming', incoming_val)
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)

    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    src_guest_session = GuestSession(case_id=id, params=params,
                                     ip=src_guest_ip)

    test.main_step_log('4.2. Start listening mode without vhost in des host ')
    params.vm_base_cmd_del('netdev', 'tap,id=tap0')
    params.vm_base_cmd_add('netdev', 'tap,id=tap0,vhost=on')
    incoming_val = 'tcp:0:%s' % (incoming_port)
    params.vm_base_cmd_add('incoming', incoming_val)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)

    test.main_step_log('4.3.Copy a large file(eg 2G) from host to guest '
                       'in src host, then start to do migration '
                       'during transferring file.')
    src_guest_session.guest_cmd_output(cmd='rm -rf /home/file_guest')
    cmd = 'dd if=/dev/urandom of=/home/file_guest ' \
          'bs=1M count=2000 oflag=direct'
    src_guest_session.guest_cmd_output(cmd, timeout=600)
    src_host_session.host_cmd_output(cmd='rm -rf /home/file_host')
    thread = threading.Thread(target=src_host_session.host_cmd_scp_get,
                              args=('/home/file_host',
                                    '/home/file_guest',
                                    params.get('guest_passwd'),
                                    src_guest_ip, 600))
    thread.name = 'scp_thread_get'
    thread.daemon = True
    thread.start()
    time.sleep(3)

    test.main_step_log('4.4. Migrate to the destination')
    check_info = do_migration(remote_qmp=src_remote_qmp,
                              migrate_port=incoming_port, dst_ip=dst_host_ip,
                              chk_timeout_2=query_migration_time)
    if (check_info == False):
        test.test_error('Migration timeout ')

    test.main_step_log('4.5.After migration finishes,until transferring finished'
                       'reboot guest,Check file in host and guest.'
                       'value of md5sum is the same.')
    while True:
        pid = src_host_session.host_cmd_output('pgrep -x scp')
        if not pid:
            break

    time.sleep(3)
    test.sub_step_log('reboot guest')
    dst_serial = RemoteSerialMonitor(case_id=id, params=params, ip=dst_host_ip,
                                     port=serial_port)
    dst_remote_qmp.qmp_cmd_output('{"execute":"system_reset"}')
    dst_guest_ip = dst_serial.serial_login()
    dst_guest_session = GuestSession(case_id=id, params=params,
                                     ip=dst_guest_ip)

    test.sub_step_log('network of guest should be woking')
    external_host_ip = 'www.redhat.com'
    cmd_ping = 'ping %s -c 10' % external_host_ip
    output = dst_guest_session.guest_cmd_output(cmd=cmd_ping)
    if re.findall(r'100% packet loss', output):
        dst_guest_session.test_error('Ping failed')

    test.sub_step_log('Check file in host and guest')
    file_src_host_md5 = src_host_session.host_cmd_output(
        cmd='md5sum /home/file_host')
    file_guest_md5 = dst_guest_session.guest_cmd_output(
        cmd='md5sum /home/file_guest')
    if file_src_host_md5.split(' ')[0] != file_guest_md5.split(' ')[0]:
        test.test_error('Value of md5sum error!')

    test.sub_step_log('4.6 quit qemu on src end and shutdown vm on dst end')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}',
                                           recv_timeout=3)
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src host')

    dst_guest_session.guest_cmd_output('shutdown -h now')
    output = dst_serial.serial_output()
    if re.findall(r'Call Trace:', output):
        test.test_error('Guest hit call trace')



