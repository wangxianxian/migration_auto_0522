from utils_host import HostSession
from utils_guest import GuestSession
from monitor import RemoteSerialMonitor, RemoteQMPMonitor
import re
from vm import CreateTest
from utils_migration import do_migration

def run_case(params):
    src_host_ip = params.get('src_host_ip')
    dst_host_ip = params.get('dst_host_ip')
    src_qemu_cmd = params.create_qemu_cmd()
    qmp_port = int(params.get('qmp_port'))
    serial_port = int(params.get('serial_port'))
    share_images_dir = params.get('share_images_dir')
    incoming_port = params.get('incoming_port')

    test = CreateTest(case_id='rhel7_10039', params=params)
    id = test.get_id()
    src_host_session = HostSession(id, params)

    test.main_step_log('1. Boot guest with one system disk.')
    src_host_session.boot_guest(cmd=src_qemu_cmd, vm_alias='src')
    src_remote_qmp = RemoteQMPMonitor(id, params, src_host_ip, qmp_port)
    test.sub_step_log('Check guest disk')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-block"}',
                                           recv_timeout=5)
    if not re.findall(r'drive_image1', output):
        src_remote_qmp.test_error('No found system disk')
    test.sub_step_log('Connecting to src serial')
    src_serial = RemoteSerialMonitor(id, params, src_host_ip, serial_port)
    src_guest_ip = src_serial.serial_login()
    dst_guest_ip = src_guest_ip

    src_guest_session = GuestSession(case_id=id, params=params, ip=src_guest_ip)
    test.sub_step_log('Check dmesg info ')
    cmd = 'dmesg'
    output = src_guest_session.guest_cmd_output(cmd)
    if re.findall(r'Call Trace:', output):
        src_guest_session.test_error('Guest hit call trace')

    test.main_step_log('2. Hot add two disk(should also in shared storage).')
    test.sub_step_log('2.1 Create two image on src host')
    src_host_session.host_cmd_output('qemu-img create '
                                     '-f qcow2 %s/data-disk0.qcow2 10G'
                                     % share_images_dir)
    src_host_session.host_cmd_output('qemu-img create '
                                     '-f qcow2 %s/data-disk1.qcow2 20G'
                                     % share_images_dir)
    test.sub_step_log('2.2 Hot plug the above disks')
    src_remote_qmp.qmp_cmd_output('{"execute":"__com.redhat_drive_add", "arguments":'
                           '{"file":"/%s/data-disk0.qcow2",'
                           '"format":"qcow2","id":"drive-virtio-blk0"}}'
                                  % share_images_dir, recv_timeout=5)
    src_remote_qmp.qmp_cmd_output('{"execute":"device_add",'
                                  '"arguments":'
                                  '{"driver":"virtio-blk-pci",'
                                  '"drive":"drive-virtio-blk0",'
                                  '"id":"virtio-blk0",'
                                  '"bus":"pci.0","addr":"10"}}',
                                  recv_timeout=5)
    src_remote_qmp.qmp_cmd_output('{"execute":"__com.redhat_drive_add", '
                                  '"arguments":'
                                  '{"file":"/%s/data-disk1.qcow2",'
                                  '"format":"qcow2","id":"drive_r4"}}'
                                  % share_images_dir, recv_timeout=5)
    src_remote_qmp.qmp_cmd_output('{"execute":"device_add",'
                                  '"arguments":'
                                  '{"driver":"scsi-hd",'
                                  '"drive":"drive_r4","id":"r4",'
                                  '"bus":"virtio_scsi_pci0.0",'
                                  '"channel":"0","scsi-id":"0","lun":"1"}}',
                                  recv_timeout=5)

    test.sub_step_log('Check the hot plug disk on src guest')
    output = src_remote_qmp.qmp_cmd_output('{"execute":"query-block"}',
                                           recv_timeout=5)
    if not re.findall(r'drive-virtio-blk0', output) \
            or not re.findall(r'drive_r4', output):
        src_remote_qmp.test_error('Hot plug disk failed on src')
        
    test.main_step_log('3. Boot \'-incoming\' guest '
                       'with disk added in step2 on des host. ')

    params.vm_base_cmd_add('drive', 'file=/%s/data-disk0.qcow2,'
                                    'format=qcow2,if=none,id=drive-virtio-blk0,'
                                    'werror=stop,rerror=stop'
                           %share_images_dir)
    params.vm_base_cmd_add('device',
                           'virtio-blk-pci,drive=drive-virtio-blk0,'
                           'id=virtio-blk0,bus=pci.0,addr=10,bootindex=10')
    params.vm_base_cmd_add('drive', 'file=/%s/data-disk1.qcow2,'
                                    'if=none,id=drive_r4,format=qcow2,'
                                    'cache=none,aio=native,'
                                    'werror=stop,rerror=stop'
                           %share_images_dir)
    params.vm_base_cmd_add('device',
                           'scsi-hd,drive=drive_r4,id=r4,'
                           'bus=virtio_scsi_pci0.0,channel=0,scsi-id=0,lun=1')
    params.vm_base_cmd_add('incoming', 'tcp:0:%s' %incoming_port)
    dst_qemu_cmd = params.create_qemu_cmd()
    src_host_session.boot_remote_guest(cmd=dst_qemu_cmd, ip=dst_host_ip,
                                       vm_alias='dst')
    dst_remote_qmp = RemoteQMPMonitor(id, params, dst_host_ip, qmp_port)

    test.main_step_log('4. Start live migration from src host')
    check_info = do_migration(src_remote_qmp, incoming_port, dst_host_ip)
    if (check_info == False):
        test.test_error('Migration timeout')

    test.sub_step_log('Login dst guest')
    test.sub_step_log('Connecting to dst serial')
    dst_serial = RemoteSerialMonitor(id, params, dst_host_ip, serial_port)
    test.sub_step_log('Check disk on dst guest')
    output = dst_remote_qmp.qmp_cmd_output('{"execute":"query-block"}',
                                           recv_timeout=5)
    if not re.findall(r'drive-virtio-blk0', output) \
            or not re.findall(r'drive_r4', output):
        src_remote_qmp.test_error('Hot plug disk failed on dst')

    cmd = 'dmesg'
    output = dst_serial.serial_cmd_output(cmd=cmd)
    if re.findall(r'Call Trace:', output) or not output:
       test.test_error('Guest hit call trace')

    test.sub_step_log('Reboot guest')
    dst_serial.serial_cmd('reboot')
    dst_guest_ip = dst_serial.serial_login()

    test.sub_step_log('Shut down dst guest and quit src qemu')
    dst_serial.serial_shutdown_vm()

    output = src_remote_qmp.qmp_cmd_output('{"execute":"quit"}')
    if output:
        src_remote_qmp.test_error('Failed to quit qemu on src end')

