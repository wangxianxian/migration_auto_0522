import time
from utils_host import HostSession
from monitor import RemoteSerialMonitor
import re
import os
from vm import CreateTest
BASE_FILE = os.path.dirname(os.path.abspath(__file__))


def run_case(params):
    serial_port = int(params.get('vm_cmd_base')
                      ['serial'][0].split(',')[0].split(':')[2])
    nfs_server_list = params.get('nfs_server')

    test = CreateTest(case_id='unattended_installation', params=params)
    id = test.get_id()

    host_session = HostSession(id, params)

    nfs_server_ip_list = []
    for server in nfs_server_list:
        nfs_server_ip_list.append(server.split(':')[0])
    test.test_print('NFS server ip:%s' % nfs_server_ip_list)

    if 'x86_64' in params.get('guest_arch'):
        params.vm_base_cmd_add('machine', 'pc')
    elif 'ppc64' in params.get('guest_arch'):
        params.vm_base_cmd_add('machine', 'pseries')

    rtt_info = {}
    rtt_val = []
    test.main_step_log('1. Chose a nfs server.')
    for ip in nfs_server_ip_list:
        ping_cmd = 'ping %s -c 5' % ip
        output = host_session.host_cmd_output(ping_cmd)
        rtt_line = output.splitlines()[-1]
        if float(rtt_line.split('/')[-3]) < float(params.get('rtt_tolerance')):
            rtt_info[ip] = rtt_line.split('/')[-3]
            rtt_val.append(float(rtt_line.split('/')[-3]))
    if not rtt_val:
        test.test_error('No available nfs server.')
    test.test_print('rtt info : %s' % rtt_info)
    min_rtt_val = min(rtt_val)
    mount_info = ''
    for ip, rtt in rtt_info.items():
        if float(rtt) == min_rtt_val:
            for nfs_server in nfs_server_list:
                if ip in nfs_server:
                    mount_info = nfs_server

    test.test_print('Mount point info : %s' % mount_info)
    image_dir = os.path.join(os.path.join(BASE_FILE, 'images'),
                             params.get('image_name'))
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    image_size = params.get('image_size')
    test.main_step_log('2. Create a system image to install os.')
    if params.get('image_format') == 'qcow2':
        image = os.path.join(image_dir, (params.get('image_name') + '.qcow2'))
        host_session.host_cmd_output('rm -rf %s' % image)
        host_session.host_cmd_output('qemu-img create -f qcow2 %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=qcow2,'
                               'file=%s' % image)

    elif params.get('image_format') == 'raw':
        image = image_dir + params.get('image_name') + '.raw'
        host_session.host_cmd_output('qemu-img create -f raw %s %s'
                                     % (image, image_size))
        params.vm_base_cmd_add('drive',
                               'id=drive_image1,if=none,snapshot=off,'
                               'aio=threads,cache=none,format=raw,'
                               'file=%s' % image)
    elif params.get('image_format') == 'luks':
        pass

    if params.get('drive_format') == 'virtio_scsi':
        params.vm_base_cmd_add('device',
                               'scsi-hd,id=image1,drive=drive_image1')
    elif params.get('drive_format') == 'virtio_blk':
        params.vm_base_cmd_add('device',
                               'virtio-blk-pci,id=image1,drive=drive_image1')

    isos_dir = os.path.join(BASE_FILE, 'isos')
    if not os.path.exists(isos_dir):
        os.makedirs(isos_dir)
        test.main_step_log('3. Mount iso from nfs server.')
    host_session.host_cmd_output('mount -t nfs %s %s' % (mount_info, isos_dir))

    test.main_step_log('4. Find the corresponding iso')
    iso_pattern = params.get('iso_name') + '*' + 'Server' + '-' \
               + params.get('guest_arch') + '-' + 'dvd1.iso'
    iso_name = host_session.host_cmd_output('find %s -name %s'
                                            % (isos_dir, iso_pattern))
    if not iso_name:
        test.test_error('No found the corresponding %s iso.'
                        % params.get('iso_name'))
    test.test_print('Found the corresponding iso: %s' % iso_name)
    params.vm_base_cmd_add('drive',
                           'id=drive_cd1,if=none,snapshot=off,aio=threads,'
                           'cache=none,media=cdrom,file=%s' % iso_name)
    params.vm_base_cmd_add('device',
                           'scsi-cd,id=cd1,drive=drive_cd1,bootindex=2')

    ks_dir = os.path.join(BASE_FILE, 'ks')
    if not os.path.exists(ks_dir):
        os.makedirs(ks_dir)
    test.main_step_log('5. Find the corresponding ks')
    ks_pattern = params.get('iso_name').split('.')[0] + '*'
    ks = host_session.host_cmd_output('find %s -name %s'
                                      % (ks_dir, ks_pattern))
    ks_iso = os.path.join(ks_dir, 'ks.iso')

    test.main_step_log('6. Make a %s form %s.' % (ks_iso, ks))
    host_session.host_cmd_output('mkisofs -o %s %s' % (ks_iso, ks))

    params.vm_base_cmd_add('drive',
                           'id=drive_unattended,if=none,snapshot=off,'
                           'aio=threads,cache=none,media=cdrom,'
                           'file=%s' % ks_iso)

    params.vm_base_cmd_add('device',
                           'scsi-cd,'
                           'id=unattended,drive=drive_unattended,bootindex=3')

    params.vm_base_cmd_add('m', params.get('mem_size'))
    params.vm_base_cmd_add('smp', '%d,cores=%d,threads=1,sockets=%d'
                           % (int(params.get('vcpu')),
                              int(params.get('vcpu'))/2,
                              int(params.get('vcpu'))/2))

    mount_dir = os.path.join(BASE_FILE, 'mnt')
    if not os.path.exists(mount_dir):
        os.makedirs(mount_dir)

    test.main_step_log('7. cp vmlinuz and initrd.img form %s.' % iso_name)
    host_session.host_cmd_output('mount %s %s' % (iso_name, mount_dir))

    if 'x86_64' in params.get('guest_arch'):
        host_session.host_cmd_output('cp /%s/images/pxeboot/vmlinuz %s'
                                     % (mount_dir, image_dir))
        host_session.host_cmd_output('cp /%s/images/pxeboot/initrd.img %s'
                                     % (mount_dir, image_dir))
        host_session.host_cmd_output('umount %s' % mount_dir)
    if 'ppc64' in params.get('guest_arch'):
        host_session.host_cmd_output('cp /%s/ppc/ppc64/vmlinuz %s'
                                     % (mount_dir, image_dir))
        host_session.host_cmd_output('cp /%s/ppc/ppc64/initrd.img %s'
                                     % (mount_dir, image_dir))
        host_session.host_cmd_output('umount %s' % mount_dir)

    test.main_step_log('8. Check the name of mounted ks.iso.')
    host_session.host_cmd_output('mount %s %s' % (ks_iso, mount_dir))
    ks_name = host_session.host_cmd_output('ls %s' % mount_dir)
    host_session.host_cmd_output('umount %s' % mount_dir)

    params.vm_base_cmd_add('kernel',
                           '"%s/vmlinuz"' % image_dir)
    console_option = ''
    if 'x86_64' in params.get('guest_arch'):
        console_option = 'ttyS0,115200'
    if 'ppc64' in params.get('guest_arch'):
        console_option = 'hvc0,38400'
    params.vm_base_cmd_add('append',
                           '"ksdevice=link inst.repo=cdrom:/dev/sr0 '
                           'inst.ks=cdrom:/dev/sr1:/%s nicdelay=60 '
                           'biosdevname=0 net.ifnames=0 '
                           'console=tty0 console=%s"'
                           % (ks_name, console_option))
    params.vm_base_cmd_add('initrd',
                           '"%s/initrd.img"' % image_dir)

    test.main_step_log('9. Boot this guest and start to install os automaticlly.')
    qemu_cmd = params.create_qemu_cmd()
    host_session.boot_guest(cmd=qemu_cmd)
    guest_serial = RemoteSerialMonitor(case_id=id,
                                       params=params, ip='0', port=serial_port)

    end_timeout = time.time() + int(params.get('install_timeout'))
    install_done = False
    while time.time() < end_timeout:
        output = guest_serial.serial_output()
        test.test_print(output)
        if re.findall(r'Power down', output):
           install_done = True
           host_session.host_cmd_output('rm -rf %s/initrd.img' % image_dir)
           host_session.host_cmd_output('rm -rf %s/vmlinuz' % image_dir)
           host_session.host_cmd_output('rm -rf %s' % ks_iso)
           break

    if install_done == False:
        host_session.host_cmd_output('rm -rf %s/initrd.img' % image_dir)
        host_session.host_cmd_output('rm -rf %s/vmlinuz' % image_dir)
        host_session.host_cmd_output('rm -rf %s' % ks_iso)
        test.test_error('Install failed under %s sec'
                        % params.get('install_timeout'))
    else:
        test.test_print('Install successfully.')
