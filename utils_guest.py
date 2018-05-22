import re
import string
from vm import TestCmd
import paramiko
from pexpect import pxssh, TIMEOUT, EOF
import socket
import os
import aexpect
import time


class GuestSession(TestCmd):
    # Class GuestSession maybe not supported in python3.6
    # and therer is a warning "No handlers could be found
    # for logger "paramiko.transport""
    def __init__(self, ip, case_id, params):
        self._ip = ip
        self._params = params
        self._passwd = params.get('guest_passwd')
        super(GuestSession, self).__init__(case_id=case_id, params=params)
        dir_timestamp = self.params.get('sub_dir_timestamp')
        sub_log_dir = os.path.join(self.params.get('log_dir'),
                                   self.case_id + '-'
                                   + dir_timestamp + '_logs')
        paramiko.util.log_to_file(os.path.join(sub_log_dir, 'paramiko.log'))
        self._ssh = paramiko.SSHClient()
        self._ssh.load_system_host_keys()
        self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._ssh.connect(hostname=ip, port=22, username='root',
                          timeout=60, password=self._passwd)

    def close(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def __del__(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def guest_cmd_output(self, cmd, verbose=True, timeout=300):
        output = ''
        errput = ''
        allput = ''
        if verbose:
            TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)

        stdin, stdout, stderr = self._ssh.exec_command(command=cmd,
                                                       timeout=timeout)
        errput = stderr.read()
        output = stdout.read()
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            if errput:
                TestCmd.test_print(self, errput)
            if output:
                TestCmd.test_print(self, output)
        allput = errput + output
        if re.findall(r'command not found', allput) or re.findall(r'-bash', allput):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return allput

    def guest_system_dev(self, verbose=True):
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd, verbose)
        system_dev = re.findall('/dev/[svh]d\w+\d+', output)[0]
        system_dev = system_dev.rstrip(string.digits)
        if verbose:
            info = 'system device : %s' % system_dev
            TestCmd.test_print(self, info=info)
        return system_dev, output

    def get_data_disk(self, verbose=True):
        data_disk = []
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd, verbose=True)
        sys_dev, _ = self.guest_system_dev(verbose=False)
        for dev in output.split('\n'):
            if sys_dev not in dev:
                data_disk.append(dev)
        if verbose:
            info = 'data disk : %s' % data_disk
            TestCmd.test_print(self, info=info)
        return data_disk

    def guest_ping_test(self, dst_ip, count):
        cmd_ping = 'ping %s -c %d' % (dst_ip, count)
        output = self.guest_cmd_output(cmd=cmd_ping)
        if re.findall(r'100% packet loss', output):
            TestCmd.test_error(self, 'Ping failed')

    def guest_dmesg_check(self):
        cmd = 'dmesg'
        output = self.guest_cmd_output(cmd)
        if re.findall(r'Call Trace:', output):
            TestCmd.test_error(self, 'Guest hit call trace')

    def guest_get_disk_size(self, dev, verbose=True):
        return self.guest_cmd_output(
            'lsblk -s %s | sed -n \'2p\' | awk {\'print $4\'}' % dev, verbose)

    def guest_create_parts(self, dev, num, fs_type='xfs', verbose=True):
        self.guest_cmd_output(cmd='parted %s -s mklabel gpt'
                                  % dev, verbose=verbose)
        dev_size = re.findall(r"\d+\.?\d*", self.guest_get_disk_size(dev))[0]
        offset_size = (int(dev_size) / num) * 1024
        start = 1
        end = offset_size
        for i in range(0, num):
            self.guest_cmd_output('parted %s -s mkpart primary %s %sMB %sMB'
                                  % (dev, fs_type, start, end), verbose)
            start = end
            end = start + offset_size
        self.guest_cmd_output('parted %s -s p' % dev)

class GuestSessionV2(TestCmd):
    # Class GuestSessionV2 is supported python2 and python3.
    # It is implemented with pexcept(Pexpect is a pure Python module
    # for spawning child applications; controlling them; and responding
    # to expected patterns in their output).
    def __init__(self, ip, case_id, params):
        self._ip = ip
        self._params = params
        self._passwd = params.get('guest_passwd')
        self._timeout = 120
        self._deadline = time.time() + self._timeout
        self._connected = False
        self._cmd = 'ssh root@%s' % self._ip
        super(GuestSessionV2, self).__init__(case_id=case_id, params=params)

        while time.time() < self._deadline:
            try:
                self._ssh = pxssh.pxssh(options={"StrictHostKeyChecking": "no",
                                                 "UserKnownHostsFile": "/dev/null"})
                self._ssh.login(server=self._ip, username='root', port=22,
                                password=self._passwd, login_timeout=60)
                self._connected = True
            except:
                time.sleep(2)
            if self._connected == True:
                break
        if self._connected == False:
            self._ssh.close()
            TestCmd.test_error(self,
                               'Failed to connect to guest session under %s sec'
                               % self._timeout)

    def close(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def __del__(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def guest_logout(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.logout()

    def guest_cmd_output(self, cmd, timeout=300):
        output = ''
        TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        self._ssh.sendline(cmd)
        if self._ssh.prompt(timeout=timeout):
            output = self._ssh.before
        else:
            TestCmd.test_error(self,
                               'Failed to run \"%s\" under %s sec.'
                               % (cmd, timeout))
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def guest_system_dev(self, enable_output=True):
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd)
        system_dev = re.findall('/dev/[svh]d\w+\d+', output)[0]
        system_dev = system_dev.rstrip(string.digits)
        if enable_output == True:
            info = 'system device : %s' % system_dev
            TestCmd.test_print(self, info=info)
        return system_dev, output

    def guest_ping_test(self, dst_ip, count):
        cmd_ping = 'ping %s -c %d' % (dst_ip, count)
        output = self.guest_cmd_output(cmd=cmd_ping)
        if re.findall(r'100% packet loss', output):
            TestCmd.test_error(self, 'Ping failed')

    def guest_dmesg_check(self):
        cmd = 'dmesg'
        output = self.guest_cmd_output(cmd)
        if re.findall(r'Call Trace:', output):
            TestCmd.test_error(self, 'Guest hit call trace')


class GuestSessionV3(TestCmd):
    # implement to connecting to guest session with axpect.
    def __init__(self, ip, case_id, params):
        self._ip = ip
        self._params = params
        self._passwd = params.get('guest_passwd')
        self._cmd = 'ssh root@%s' % self._ip
        super(GuestSessionV3, self).__init__(case_id=case_id, params=params)


        cmd = ("ssh -o UserKnownHostsFile=/dev/null "
               "-o PreferredAuthentications=password -p %s %s@%s" % (22, 'root', ip))
        self._ssh = aexpect.ShellSession(cmd)
        try:
            self._handle_prompts('root', self._passwd, 30)
            TestCmd.test_print(self, 'Connect guest session successfully.')
        except Exception:
            self._ssh.close()
            TestCmd.test_error(self, 'Failed to ssh guest session.')

    def _handle_prompts(self, username, password, timeout=60):
        password_prompt_count = 0
        login_prompt_count = 0
        while True:
            try:
                match, text = self._ssh.read_until_last_line_matches(
                    [r"[Aa]re you sure",
                     r"[Pp]assword:\s*",
                     r"(?<![Ll]ast).*[Ll]ogin:\s*$",
                     r"[Cc]onnection.*closed",
                     r"[Cc]onnection.*refused",
                     r"[Ww]arning",
                     r"[Ee]nter.*username",
                     r"[Ee]nter.*password"],
                    timeout=timeout, internal_timeout=0.5)
                if match == 0:  # "Are you sure you want to continue connecting"
                    self._ssh.sendline("yes")
                    continue
                elif match == 1 or match == 8:  # "password:"
                    if password_prompt_count == 0:
                        self._ssh.sendline(password)
                        password_prompt_count += 1
                        break
                    else:
                        pass
                elif match == 2 or match == 7:  # "login:"
                    if login_prompt_count == 0 and password_prompt_count == 0:
                        self._ssh.sendline(username)
                        login_prompt_count += 1
                        continue
                    else:
                        pass
                elif match == 3:  # "Connection closed"
                    TestCmd.test_error(self, "Client said 'connection closed'")
                    break
                elif match == 4:  # "Connection refused"
                    TestCmd.test_error(self, "Client said 'connection refused'")
                    break
                elif match == 6:  # "Warning added RSA"
                    TestCmd.test_print(self,
                                       "Got 'Warning added RSA to known host list")
                    break
            except aexpect.ExpectTimeoutError as e:
                TestCmd.test_error(self, e.output)
            except aexpect.ExpectProcessTerminatedError as e:
                TestCmd.test_error(self, e.output)


    def close(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def __del__(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def guest_logout(self):
        TestCmd.test_print(self,
                        'Closed the guest session(%s).' % (self._ip))
        self._ssh.close()

    def guest_cmd_output_safe(self, cmd, timeout=300, verbose=True):
        output = ''
        if verbose:
            TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        output = self._ssh.cmd_output_safe(cmd=cmd, timeout=timeout)
        if not output:
            TestCmd.test_error(self,
                               'Failed to run \"%s\" under %s sec.'
                               % (cmd, timeout))
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def guest_cmd_status_output(self, cmd, timeout=300, verbose=True):
        output = ''
        if verbose:
            TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        output = self._ssh.cmd_status_output(cmd=cmd, timeout=timeout)
        if not output:
            TestCmd.test_error(self,
                               'Failed to run \"%s\" under %s sec.'
                               % (cmd, timeout))
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def guest_cmd_status(self, cmd, timeout=300, verbose=True):
        output = ''
        if verbose:
            TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        output = self._ssh.cmd_status(cmd=cmd, timeout=timeout)
        if not output:
            TestCmd.test_error(self,
                               'Failed to run \"%s\" under %s sec.'
                               % (cmd, timeout))
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def guest_cmd_output(self, cmd, timeout=300, verbose=True):
        output = ''
        if verbose:
            TestCmd.test_print(self, '[root@guest ~]# %s' % cmd)
        output = self._ssh.cmd_output(cmd=cmd, timeout=timeout)
        output = re.sub(r'^Last login.*\s+', '', output)
        output = re.sub(r'\s*\[.*@.*~\]# ', '', output)
        if not output:
            TestCmd.test_error(self,
                               'Failed to run \"%s\" under %s sec.'
                               % (cmd, timeout))
        # Here need to remove command echo and blank space again
        output = TestCmd.remove_cmd_echo_blank_space(self, output=output, cmd=cmd)
        if verbose:
            TestCmd.test_print(self, output)
        if re.findall(r'command not found', output) or re.findall(r'-bash', output):
            TestCmd.test_error(self, 'Command %s failed' % cmd)
        return output

    def guest_system_dev(self, verbose=True):
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd, verbose=verbose)
        system_dev = re.findall('/dev/[svh]d\w+\d+', output)[0]
        system_dev = system_dev.rstrip(string.digits)
        if verbose:
            info = 'system device : %s' % system_dev
            TestCmd.test_print(self, info=info)
        return system_dev, output

    def get_data_disk(self, verbose=True):
        data_disk = []
        cmd = 'ls /dev/[svh]d*'
        output = self.guest_cmd_output(cmd, verbose=True)
        sys_dev, _ = self.guest_system_dev(verbose=False)
        for dev in output.split('\n'):
            if sys_dev not in dev:
                data_disk.append(dev)
        if verbose:
            info = 'data disk : %s' % data_disk
            TestCmd.test_print(self, info=info)
        return data_disk

    def guest_ping_test(self, dst_ip, count):
        cmd_ping = 'ping %s -c %d' % (dst_ip, count)
        output = self.guest_cmd_output(cmd=cmd_ping)
        if re.findall(r'100% packet loss', output):
            TestCmd.test_error(self, 'Ping failed')

    def guest_dmesg_check(self):
        cmd = 'dmesg'
        output = self.guest_cmd_output(cmd)
        if re.findall(r'Call Trace:', output):
            TestCmd.test_error(self, 'Guest hit call trace')

    def guest_get_disk_size(self, dev, verbose=True):
        return self.guest_cmd_output(
            'lsblk -s %s | sed -n \'2p\' | awk {\'print $4\'}' % dev, verbose)

    def guest_create_parts(self, dev, num, fs_type='xfs', verbose=True):
        self.guest_cmd_output(cmd='parted %s -s mklabel gpt'
                                  % dev, verbose=verbose)
        dev_size = re.findall(r"\d+\.?\d*", self.guest_get_disk_size(dev))[0]
        offset_size = (int(dev_size) / num) * 1024
        start = 1
        end = offset_size
        for i in range(0, num):
            self.guest_cmd_output('parted %s -s mkpart primary %s %sMB %sMB'
                                  % (dev, fs_type, start, end), verbose)
            start = end
            end = start + offset_size
        self.guest_cmd_output('parted %s -s p' % dev)