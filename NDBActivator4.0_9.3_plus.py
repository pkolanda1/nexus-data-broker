"""
Validated NDB Release(s): NDB 3.10.0, NDB 3.10.1
Script is to deploy NDB Embedded on the Guestshell for the first time
Usage for NDB 3.10.0:   python bootflash:<Activator_script> -v guestshell+ <NDB_embedded_zip_file>
                        [<jre_tar.gz_file> <unzip_rpm_file>] [--force] [--quiet]
Usage for NDB 3.10.1 and above: python bootflash:<Activator_script> -v guestshell+ <NDB_embedded_zip_file>
                        [--force] [--quiet]
"""

import json
import subprocess
import re
import os
import sys
import copy
import time
import logging
import zipfile
import fileinput
from cli import *

class Nexus(object):
    """Class to perform nexus switch related operations"""
    def __init__(self):
        self.user = None
        self.vs_data = None
        self.n3k_flag = 0
        self.n9k_flag = 0

    def get_vs_info(self):
        """Collect the virtual service cpu/memory/disk size"""
        self.vs_data = None
        vs_memory_cmd = 'show virtual-service global | json'
        try:
            self.vs_data = cli(vs_memory_cmd)
            self.vs_data = json.loads(self.vs_data)
        except:
            logger.error("Something went wrong while fetching switch memory")
        return self.vs_data

    def get_vs_memory_quota(self, vs_info=None):
        """Returns the available memory quota for Virtual-service"""
        memory_quota = None
        if vs_info is None:
            self.vs_data = self.get_vs_info()
        else:
            self.vs_data = copy.deepcopy(vs_info)
        vs_items = self.vs_data['TABLE_resource_limits']['ROW_resource_limits']
        for resource_item in vs_items:
            if 'memory' in resource_item['media_name']:
                memory_quota = resource_item['quota']
        return memory_quota

    def get_vs_disk_quota(self, vs_info=None):
        """Returns the available disk quota for Virtual-service"""
        disk_quota = None
        if vs_info is None:
            self.vs_data = self.get_vs_info()
        else:
            self.vs_data = copy.deepcopy(vs_info)
        vs_items = self.vs_data['TABLE_resource_limits']['ROW_resource_limits']
        for resource_item in vs_items:
            if 'bootflash' in resource_item['media_name']:
                disk_quota = resource_item['quota']
        return disk_quota

    def get_vs_cpu_quota(self, vs_info=None):
        """Returns the available cpu quota for Virtual-service"""
        cpu_quota = None
        if vs_info is None:
            self.vs_data = self.get_vs_info()
        else:
            self.vs_data = copy.deepcopy(vs_info)
        vs_items = self.vs_data['TABLE_resource_limits']['ROW_resource_limits']
        for resource_item in vs_items:
            if 'system CPU' in resource_item['media_name']:
                cpu_quota = resource_item['quota']
        return cpu_quota

    def get_user(self):
        """Returns the current username"""
        current_user = subprocess.check_output("whoami", shell=True)
        self.user = current_user.strip()
        return self.user

    def get_role(self, user=None):
        """Returns the role of a given user"""
        user_roles = None
        if user:
            self.user = user
        if self.user:
            roles_cmd = 'show user-account '+ self.user +' | json'
            try:
                roles_resp = cli(roles_cmd)
                roles = json.loads(roles_resp)
                user_roles = roles['TABLE_template']['ROW_template'][
                    'TABLE_role']['ROW_role']
            except:
                logger.error("Something went wrong while fetching user roles")
        else:
            logger.error("Please specify valid user")
        return user_roles

    def get_privilege(self):
        """Returns the privilege of a given user"""
        user_priv = None
        priv_cmd = 'show privilege'
        try:
            priv_resp = cli(priv_cmd)
            for line in priv_resp.split("\n"):
                line = line.strip()
                if "privilege level" in line:
                    user_priv = line.split(":")[1]
        except:
            logger.info("Something went wrong while fetching user privilege")
        return user_priv

    def get_nxos_version(self):
        """Returns the NXOS version of switch"""
        version = None
        version_cmd = 'show version | json'
        try:
            version_resp = cli(version_cmd)
            version_resp = json.loads(version_resp)
            version = version_resp['kickstart_ver_str']
        except:
            logger.error("Something went wrong while fetching NXOS version")
        return version

    def get_nxos_platform(self):
        """Returns the NXOS platform of switch"""
        platform = None
        platform_cmd = 'sh ver | inc ignore-case Chassis'
        try:
            cliout = cli(platform_cmd)
            for line in cliout.split("\n"):
                line = line.strip()
                if ("Chassis" in line or 'chassis' in line) and 'cisco' in line:
                    if len(line.split()) >= 4:
                        platform = line.split()[2]
                    else:
                        platform = line.split()[1]
        except:
            pass
        return platform

    def enable_nxapi_feature(self):
        """Enables feature nxapi"""
        nxapi_cmd = 'configure terminal ; feature nxapi'
        try:
            cli(nxapi_cmd)
            return True
        except:
            logger.error("Something went wrong while enabling feature NX-API")
            return False

    def enable_bash_shell(self):
        """Enables feature nxapi"""
        bash_cmd = 'configure terminal ; feature bash-shell'
        try:
            cli(bash_cmd)
            return True
        except:
            logger.error("Something went wrong while enabling feature bash-shell")
            return False

    def set_nxapi_vrf(self):
        """Configures vrf to be used for nxapi communication"""
        vrf_cmd = 'configure terminal ; nxapi use-vrf management ; copy running-config startup-config'
        try:
            cli(vrf_cmd)
            return True
        except:
            logger.error("Something went wrong while keeping nxapi to listen to network namespace")
            return False

    def remove_file(self, name):
        """Remove a file/directory from bootflash"""
        file_name = name
        remove_cmd = 'sudo rm -rf /bootflash/' + file_name
        try:
            subprocess.check_output(remove_cmd, shell=True)
            return True
        except:
            return False

    def check_file(self, name):
        """check a file/directory from bootflash"""
        file_name = name
        file_path = '/bootflash/' + file_name
        try:
            return bool(os.path.exists(file_path))
        except:
            return False

    def modify_content(self, user, embedded_path):
        """Replace the content of the files in ndb/embedded/i5 directory"""
        try:
            make_path = embedded_path + '/make-systemctl-env.sh'
            if bool(os.path.exists(make_path)):
                for line in fileinput.input(make_path, inplace=1):
                    print line.replace("guestshell", user)
            service_path = embedded_path + '/ndb.service'
            if bool(os.path.exists(service_path)):
                for line in fileinput.input(service_path, inplace=1):
                    print line.replace("guestshell", user)
            trigger_path = embedded_path + 'trigger.sh'
            if bool(os.path.exists(trigger_path)):
                for line in fileinput.input(trigger_path, inplace=1):
                    print line.replace("guestshell", user)
            return True
        except:
            return False

class Guestshell(Nexus):
    """Performs guestshell related operations in nexus switch"""
    def __init__(self):
        super(Guestshell, self).__init__()
        self.status = None
        self.reserved_cpu = None
        self.reserved_memory = None
        self.reserved_disk = None
        self.guestshell_version = None

    def get_cpu(self):
        """Get the reserved cpu value for guestshell"""
        status_cmd = 'show virtual-service detail name guestshell+ | json'
        guestshell_cpu = None
        try:
            guestshell_resp = cli(status_cmd)
            if guestshell_resp != '':
                guestshell_resp = json.loads(guestshell_resp)
                guestshell_cpu = guestshell_resp['TABLE_detail']['ROW_detail']['cpu_reservation']
            self.reserved_cpu = guestshell_cpu
            return self.reserved_cpu
        except:
            logger.error("Something went wrong while fetching guestshell+ reserved cpu")

    def get_memory(self):
        """Get the reserved memory value for guestshell"""
        status_cmd = 'show virtual-service detail name guestshell+ | json'
        guestshell_memory = None
        try:
            guestshell_resp = cli(status_cmd)
            if guestshell_resp != '':
                guestshell_resp = json.loads(guestshell_resp)
                guestshell_memory = guestshell_resp['TABLE_detail'][
                    'ROW_detail']['memory_reservation']
            self.reserved_memory = guestshell_memory
            return self.reserved_memory
        except:
            logger.error("Something went wrong while fetching guestshell+ reserved memory")

    def get_disk(self):
        """Get the reserved disk value for guestshell"""
        status_cmd = 'show virtual-service detail name guestshell+ | json'
        try:
            guestshell_resp = cli(status_cmd)
            if guestshell_resp != '':
                guestshell_resp = json.loads(guestshell_resp)
                guestshell_disk = guestshell_resp['TABLE_detail']['ROW_detail']['disk_reservation']
            self.reserved_disk = guestshell_disk
            return self.reserved_disk
        except:
            logger.error("Something went wrong while fetching guestshell+ reserved memory")

    def set_cpu(self, cpu_value):
        """Set the cpu value for guestshell"""
        cpu_cmd = 'guestshell resize cpu ' + str(cpu_value)
        try:
            cli(cpu_cmd)
            return True
        except:
            logger.error("Something went wrong while configuring cpu for guestshell+")
            return False

    def set_memory(self, memory_value):
        """Set the cpu value for guestshell"""
        memory_cmd = 'guestshell resize memory ' + str(memory_value)
        try:
            cli(memory_cmd)
            return True
        except:
            logger.error("Something went wrong while configuring memory for guestshell+")
            return False

    def set_disk(self, disk_value):
        """Set the cpu value for guestshell"""
        disk_cmd = 'guestshell resize rootfs ' + str(disk_value)
        try:
            cli(disk_cmd)
            return True
        except:
            logger.error("Something went wrong while configuring bootflash for guestshell+")
            return False

    def enable(self, pkg_name=None):
        """Enables the guestshell"""
        enable_cmd = 'guestshell enable'
        if pkg_name:
            enable_cmd = 'guestshell enable package ' + pkg_name
        try:
            cli(enable_cmd)
            return True
        except:
            logger.error("Something went wrong while enabling guestshell")
            return False

    def disable(self):
        """Disables the guestshell"""
        disable_cmd = 'guestshell disable'
        try:
            cli(disable_cmd)
            return True
        except:
            logger.error("Something went wrong while disabling guestshell")

    def reboot(self):
        """Rebooting the guestshell"""
        reboot_cmd = 'guestshell reboot'
        try:
            cli(reboot_cmd)
            return True
        except:
            logger.error("Something went wrong while rebooting guestshell")

    def get_status(self):
        """Get the status of the guestshell"""
        status_cmd = 'show virtual-service detail name guestshell+ | json'
        guestshell_status = None
        try:
            guestshell_resp = cli(status_cmd)
            if guestshell_resp == '':
                guestshell_status = 'Not Installed'
            else:
                guestshell_resp = json.loads(guestshell_resp)
                guestshell_status = guestshell_resp['TABLE_detail']['ROW_detail']['state']
            self.status = guestshell_status
            return self.status
        except:
            logger.error("Something went wrong while fetching guestshell+ status")

    def get_version(self):
        """Get the version of guestshell"""
        status_cmd = 'show virtual-service detail name guestshell+ | json'
        guestshell_version = None
        try:
            guestshell_resp = cli(status_cmd)
            if guestshell_resp != '':
                guestshell_resp = json.loads(guestshell_resp)
                guestshell_version = guestshell_resp['TABLE_detail'][
                    'ROW_detail']['application_version']
            self.guestshell_version = guestshell_version
            return self.guestshell_version
        except:
            logger.error("Something went wrong while fetching guestshell+ reserved cpu")

    def gs_copy_ndb(self, from_path, to_path):
        """Proc to copy file from one location to another"""
        copy_cmd = 'guestshell run sudo cp -Rf ' + from_path + " " + to_path + "/"
        try:
            cli(copy_cmd)
            return True
        except:
            return False

    def change_ndb_perm(self, guest_path):
        """Proc to change the directory permission through guestshell"""
        perm_cmd = 'guestshell run sudo chmod -Rf 777 ' + guest_path
        try:
            cli(perm_cmd)
            return True
        except:
            return False

class NDB(Guestshell):
    """Performs NDB related operations inside Guestshell"""
    def __init__(self):
        super(NDB, self).__init__()
        self.ndb_version = None

    def extract_ndb(self, file_name, path_to_extract):
        """Extract the NDB zip file to given path"""
        try:
            zip_ref = zipfile.ZipFile(file_name, 'r')
            zip_ref.extractall(path_to_extract)
            zip_ref.close()
            return True
        except:
            return False

    def validate_ndb_content(self, path):
        """Check for the files inside ndb directory"""
        try:
            ndbpath = path
            files = ('runndb.sh', 'start.sh', 'version.properties', 'runndb.bat')
            for file_name in files:
                file_path = ndbpath + '/' + file_name
                if not os.path.exists(file_path):
                    logger.debug(file_path)
                    return False
            fd = os.open(ndbpath + '/version.properties', os.O_RDWR)
            ndb_ver = os.read(fd, 35)
            os.close(fd)
            # logger.info(ndb_ver)
            if "com.cisco.csdn.ndb.version = 3.10.0" in ndb_ver:
                dirs = ('embedded', 'lib', 'bin', 'configuration', 'etc', 'plugins')
            else:
                dirs = ('embedded', 'lib', 'bin', 'configuration', 'plugins')
            for dir_name in dirs:
                dir_path = ndbpath + '/' + dir_name
                if not os.path.isdir(dir_path):
                    logger.debug(dir_path)
                    return False
            return True
        except:
            return False

    def install_jre(self, install_flag, jre_file):
        """Setting up JRE for NDB 3.10.0"""
        if install_flag and "tar.gz" in jre_file:
            logger.info("Extracting JAVA - offline mode")
            install_jre_cmd0 = 'guestshell run sudo mkdir -p /usr/bin/jre'
            cli(install_jre_cmd0)
            install_jre_cmd1 = 'guestshell run sudo tar -xvzf '+ jre_file + ' --directory /usr/bin/jre/ --no-same-owner'
            cli(install_jre_cmd1)
            install_jre_cmd2 = 'guestshell run sudo ls /usr/bin/jre/'
            val = cli(install_jre_cmd2)
            install_jre_cmd = 'guestshell run sudo ln -s /usr/bin/jre/' + val.strip() + '/bin/java /usr/bin/java -f'
        else:
            logger.info("Installing JAVA - online mode")
            install_jre_cmd = 'guestshell run sudo ip netns exec management yum -y install java-1.8.0-openjdk'
        try:
            v=cli(install_jre_cmd)
            if "fail" in v:
                if 'Complete!' not in v:
                    if 'Could not resolve host' in v:
                        logger.error("Could not reach repository for installing Java, refer ndb_deploy.log in bootflash for more details")
                    else:
                        logger.error("Something went wrong while installing Java, refer ndb_deploy.log in bootflash for more details")
                    logger.debug(v)
                    return False
            return True
        except:
            return False

    def install_unzip(self, install_flag, unzip_file):
        """Installing unzip package"""
        if install_flag:
            logger.info("Installing unzip package - offline mode")
            install_unzip_cmd = 'guestshell run sudo rpm -ivh ' + unzip_file
        else:
            logger.info("Installing unzip package - online mode")
            install_unzip_cmd = 'guestshell run sudo ip netns exec management yum -y install unzip'
        try:
            v=cli(install_unzip_cmd)
            if "fail" in v:
                logger.debug(v)
                return False
            return True
        except:
            return False

    def start_ndb(self, path):
        """Starting the NDB"""
        start_cmd = 'guestshell run ' + path + '/embedded/i5/make-systemctl-env.sh'
        try:
            cli(start_cmd)
            return True
        except:
            return False

    def verify_ndb(self):
        """Verifying if NDB is already installed"""
        systemd_path = '/isan/vdc_1/virtual-instance/guestshell+/rootfs/usr/lib/systemd/system/ndb.service'
        return bool(os.path.exists(systemd_path))

def validate_gs_version(version):
    """Returns True if guestshell version is equal to or greater than 2.2(0.2)"""
    guestshell_version = version
    version_pattern = r"(\d+).(\d+)"
    versions = re.findall(version_pattern, guestshell_version)
    version1 = list(versions[0])
    major_version1 = version1[0]
    minor_version1 = version1[1]
    expected_major_version1 = 2
    expected_minor_version1 = 2
    val = str(major_version1) + "." + str(minor_version1)
    flag = False
    if val == "2.2":
        version2 = list(versions[1])
        major_version2 = version2[0]
        minor_version2 = version2[1]
        expected_major_version2 = 0
        expected_minor_version2 = 2
        if int(major_version2) > int(expected_major_version2):
            flag = True
        elif int(major_version2) == int(expected_major_version2):
            if int(minor_version2) >= int(expected_minor_version2):
                flag = True
    else:
        if int(major_version1) > int(expected_major_version1):
            flag = True
        elif int(major_version1) == int(expected_major_version1):
            if int(minor_version1) >= int(expected_minor_version1):
                flag = True
    return flag

def wait_gs_up(gs_obj):
    """Waits for the guestshell to be UP"""
    status_check_count = 36
    check_interval = 5
    activated_flag = 0
    for _ in xrange(status_check_count):
        gs_status = gs_obj.get_status()
        if gs_status == 'Activated':
            activated_flag = 1
            break
        else:
            time.sleep(check_interval)
    return bool(activated_flag)

def allocate_gs_resource(gs_obj):
    """Allocate guestshell resource based on available quota"""
    min_memory = 1024
    min_disk = 1024
    min_cpu = 5
    skip_memory = 0
    skip_disk = 0
    skip_cpu = 0
    set_flag = 1
    memory_quota = gs_obj.get_vs_memory_quota()
    disk_quota = gs_obj.get_vs_disk_quota()
    cpu_quota = gs_obj.get_vs_cpu_quota()
    committed_memory = gs_obj.get_memory()
    committed_disk = gs_obj.get_disk()
    committed_cpu = gs_obj.get_cpu()
    if int(memory_quota) < min_memory:
        set_resp = gs_obj.set_memory(memory_quota)
        gs_obj.n3k_flag = 1
        gs_obj.n9k_flag = 0
        if not set_resp:
            set_flag = 0
    else:
        gs_obj.n9k_flag = 1
        gs_obj.n3k_flag = 0
        if int(committed_memory) >= min_memory:
            skip_memory = 1
        else:
            set_resp = gs_obj.set_memory(min_memory)
            if not set_resp:
                set_flag = 0
    if int(disk_quota) < min_disk:
        set_resp = gs_obj.set_disk(disk_quota)
        if not set_resp:
            set_flag = 0
    else:
        if int(committed_disk) >= min_disk:
            skip_disk = 1
        else:
            set_resp = gs_obj.set_disk(min_disk)
            if not set_resp:
                set_flag = 0
    if int(cpu_quota) < min_cpu:
        set_resp = gs_obj.set_cpu(cpu_quota)
        if not set_resp:
            set_flag = 0
    else:
        if int(committed_cpu) >= min_cpu:
            skip_cpu = 1
        else:
            set_resp = gs_obj.set_cpu(min_cpu)
            if not set_resp:
                set_flag = 0
    if skip_cpu and skip_disk and skip_memory:
        return True, gs_obj
    elif set_flag:
        reboot_resp = gs_obj.reboot()
        if reboot_resp:
            wait_resp = wait_gs_up(gs_obj)
            return wait_resp, gs_obj
        else:
            return False, gs_obj

def add_content(nexus_obj, path):
    """Adds platform and flag for NXOS"""
    try:
        ndbpath = path
        platform_string = "Platform="
        platform = nexus_obj.get_nxos_platform()
        if not platform:
            return False
        platform = int(re.search(r'\d+', platform).group())
        platform_string += str(platform)+'\n'
        platform_file = ndbpath + "/embedded/Platform"
        file_obj = open(platform_file, "w+")
        n3k_string = 'n3k_conf_flag='+str(nexus_obj.n3k_flag)+'\n'
        n9k_string = 'n9k_conf_flag='+str(nexus_obj.n9k_flag)+'\n'
        platform_content = [platform_string, n9k_string, n3k_string]
        file_obj.writelines(platform_content)
        file_obj.close()
        return True
    except:
        return False

def guestshell():
    """Perform all guestshell operation to start NDB"""
    ndb_obj = NDB()
    force_flag = 0
    install_flag=0
    jre_file = "online"
    unzip_file = "online"
    if '--help' in sys.argv:
        logger.info(
            "Supported NDB versions: NDB 3.10.0 and above\n"
            "Usage for NDB 3.10.0 alone: python bootflash:<Activator_script> -v guestshell+ <NDB_embedded_zip_file> "
            "[<jre_tar.gz_file> <unzip_rpm_file>] [--force] [--quiet]\n"
            "Usage for NDB 3.10.1 and above: python bootflash:<Activator_script> -v guestshell+ <NDB_embedded_zip_file>"
            " [--force] [--quiet]")
        sys.exit(0)
    if len(sys.argv) == 4:
        zip_file_path = sys.argv[-1]
    elif len(sys.argv) == 5 and '--force' in sys.argv[-1]:
        zip_file_path = sys.argv[-2]
        force_flag = 1
    elif len(sys.argv) == 5 and '--quiet' in sys.argv[-1]:
        zip_file_path = sys.argv[-2]
    elif len(sys.argv) == 6 and '--force' not in sys.argv[-1] and '--quiet' not in sys.argv[-1]:
        zip_file_path = sys.argv[-3]
        jre_file = sys.argv[-2]
        install_flag = 1
        unzip_file = sys.argv[-1]
    elif len(sys.argv) == 7 and '--force' in sys.argv[-1]:
        zip_file_path = sys.argv[-4]
        jre_file = sys.argv[-3]
        install_flag = 1
        unzip_file = sys.argv[-2]
        force_flag = 1
    elif len(sys.argv) == 7 and '--quiet' in sys.argv[-1]:
        zip_file_path = sys.argv[-4]
        jre_file = sys.argv[-3]
        install_flag = 1
        unzip_file = sys.argv[-2]
    else:
        logger.error("Provided arguments are not valid")
        logger.info(
            "Supported NDB versions: NDB 3.10.0 and above\n"
            "Usage for NDB 3.10.0 alone: python bootflash:<Activator_script> -v guestshell+ <NDB_embedded_zip_file> "
            "[<jre_tar.gz_file> <unzip_rpm_file>] [--force] [--quiet]\n"
            "Usage for NDB 3.10.1 and above: python bootflash:<Activator_script> -v guestshell+ <NDB_embedded_zip_file>"
            " [--force] [--quiet]")
        sys.exit(0)
    if not os.path.exists(zip_file_path):
        logger.error("NDB zip file does not exists in the given path " + zip_file_path)
        sys.exit(0)
    if install_flag == 1 and "ndb1000-sw-app-emb-9.3-plus-k9-3.10.0.zip" in zip_file_path:
        if "tar.gz" not in jre_file:
            logger.error("Provided jre file is invalid.")
            sys.exit(0)
        elif not os.path.exists(jre_file):
            logger.error("jre tar.gz file does not exists in the given path "+ jre_file)
            sys.exit(0)
    if install_flag == 1 and "ndb1000-sw-app-emb-9.3-plus-k9-3.10.0.zip" in zip_file_path:
        if "rpm" not in unzip_file:
            logger.error("Provided unzip package is invalid")
            sys.exit(0)
        elif not os.path.exists(unzip_file):
            logger.error("unzip rpm file does not exists in the given path " + unzip_file)
            sys.exit(0)
    c_user = ndb_obj.get_user()
    if not c_user:
        logger.error("Something went wrong while fetching current user")
        sys.exit(0)
    # Check the current user role
    c_user_role = ndb_obj.get_role()
    if type(c_user_role)==list:
        for roles in c_user_role:
            if "network-admin" in roles["role"]:
                c_user_role = "network-admin"
    else:
        c_user_role = c_user_role["role"]
    if 'network-admin' not in c_user_role:
        logger.error("User role is not network-admin")
        sys.exit(0)
    
    try:
        privilege = ndb_obj.get_privilege()
        if int(privilege) != 15:
            logger.error("User privilege is not 15")
            sys.exit(0)
    except:
        logger.info("Show privilege validation skipped")
    # Check whether the guestshell is activated
    current_gs_status = ndb_obj.get_status()
    if current_gs_status == 'Activated':
        pass
    else:
        # Enabling Guestshell in the switch
        logger.info("Enabling Guestshell")
        enable_resp = ndb_obj.enable()
        state_flag = 0
        if enable_resp:
            wait_resp = wait_gs_up(ndb_obj)
            if wait_resp:
                state_flag = 1
        if not state_flag:
            logger.error("Something went wrong while enabling Guestshell")
            sys.exit(0)
    # Validate the current GS version
    gs_version = ndb_obj.get_version()
    logger.info("Validating Guestshell version")
    validate_resp = validate_gs_version(gs_version)
    if not validate_resp:
        logger.error("NDB doesn't support current Guestshell version")
        logger.error("NDB will run on Guestshell version 2.2 and above, either upgrade the Guestshell or destroy and re-run the script")
        sys.exit(0)
    if not force_flag:
        allocate_resp, ndb_obj = allocate_gs_resource(ndb_obj)
        if allocate_resp:
            logger.info("Resized the guestshell resources")
        else:
            logger.error("Something went wrong while allocating Guestshell resource")
            sys.exit(0)
    check_file_resp = ndb_obj.check_file('ndb')
    if check_file_resp:
        logger.error("Directory ndb already present in bootflash. Please remove it.")
        sys.exit(0)

    if "ndb1000-sw-app-emb-9.3-plus-k9-3.10.0.zip" in zip_file_path:
        # JRE installation
        jre_resp = ndb_obj.install_jre(install_flag, jre_file)
        if not jre_resp:
            if not install_flag:
                logger.info("To install Java, either provide internet connectivity or run activator script with JRE tar.gz file as argument")
            sys.exit(0)
        # unzip package installation
        unzip_resp = ndb_obj.install_unzip(install_flag, unzip_file)
        if not unzip_resp:
            logger.error("Something went wrong while installing unzip package, refer ndb_deploy.log in bootflash for more details")
            if not install_flag:
                logger.error("To install unzip package, either provide internet connectivity or run activator script with unzip rpm package as argument")
            sys.exit(0)
    else:

        check_bash = cli("sh running-config | grep bash-shell")
        if check_bash != "feature bash-shell":
            bash_resp = ndb_obj.enable_bash_shell()
            if not bash_resp:
                logger.error("Something went wrong while enabling feature bash-shell in switch")


        cmd0 = "run bash mkdir -p /bootflash/temp_unzip"
        cli(cmd0)
        cmd1 = "run bash cp $(which unzip) /bootflash/temp_unzip/unzip"
        cli(cmd1)
        cmd2 = "guestshell run sudo cp /bootflash/temp_unzip/unzip /usr/bin"
        cli(cmd2)
        perm_cmd = 'guestshell run sudo chmod -Rf 777 /usr/bin/unzip'
        cli(perm_cmd)
        cmd3 = "guestshell run sudo rm -rf /bootflash/temp_unzip/"
        cli(cmd3)
        logger.debug("Copied the Unzip package into the /usr/bin directory")

    # Unzipping NDB zip file to Guestshell bootflash
    extract_resp = ndb_obj.extract_ndb(zip_file_path, '/bootflash')
    ndb_path = '/bootflash/ndb'
    guest_path = '/usr/bin'
    # Verifying NDB is already installed
    if not force_flag:
        verify_ndb_resp = ndb_obj.verify_ndb()
        if verify_ndb_resp:
            logger.error("NDB application is already installed.")
            ndb_obj.remove_file('ndb')
            sys.exit(0)
    if extract_resp:
        # Validate the content in ndb dir
        if not os.path.exists(ndb_path):
            logger.error("Zip file "+ zip_file_path +" doesn't contain ndb. Provide valid zip file")
            ndb_obj.remove_file('ndb')
            sys.exit(0)
        validate_resp = ndb_obj.validate_ndb_content(ndb_path)
        if not validate_resp:
            logger.error("Some files are missing in ndb. Provide valid zip file")
            ndb_obj.remove_file('ndb')
            sys.exit(0)
    else:
        # add the actual value instead of generic zip file
        logger.error("Something went wrong while extracting zip file "+ zip_file_path)
        ndb_obj.remove_file('ndb')
        sys.exit(0)

    embedded_path = ndb_path + '/embedded/i5'
    modify_resp = ndb_obj.modify_content(c_user, embedded_path)
    if not modify_resp:
        logger.error("Something went wrong while replacing file information under ndb/embedded directory")
        ndb_obj.remove_file('ndb')
        sys.exit(0)
    add_resp = add_content(ndb_obj, ndb_path)
    if not add_resp:
        logger.warning("Something went wrong while adding platform information under ndb/embedded directory")
    # Copying ndb directory to guestshell
    copy_resp = ndb_obj.gs_copy_ndb(ndb_path, guest_path)
    if not copy_resp:
        logger.error("Something went wrong while copying ndb to guestshell path")
        ndb_obj.remove_file('ndb')
        sys.exit(0)
    else:
        logger.info("Placed the ndb folder into the /usr/bin directory")
        # Remove ndb directory from bootflash
        remove_resp = ndb_obj.remove_file('ndb')
        if not remove_resp:
            logger.error("Something went wrong while removing ndb from bootflash")
    ndb_path = '/usr/bin/ndb'
    ndb_perm_resp = ndb_obj.change_ndb_perm(ndb_path)
    if not ndb_perm_resp:
        logger.error("Something went wrong while changing the permission of ndb directory")
    nxapi_resp = ndb_obj.enable_nxapi_feature()
    if not nxapi_resp:
        logger.error("Something went wrong while enabling feature nxapi in switch")
    vrf_resp = ndb_obj.set_nxapi_vrf()
    if vrf_resp:
        logger.info("Kept the nxapi to listen to network namespace")
    else:
        logger.error("Something went wrong while keeping nxapi to listen to network namespace")
        sys.exit(0)
    start_resp = ndb_obj.start_ndb(ndb_path)
    if start_resp:
        logger.info("Started NDB")
    else:
        logger.error("Something went wrong while starting NDB as a service")
        sys.exit(0)

def main():
    """Function which triggers guestshell proc to start NDB"""
    guestshell()

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    con_log_handler = logging.StreamHandler()
    file_log_handler = logging.FileHandler("/bootflash/ndb_deploy.log")
    file_log_handler.setLevel(logging.DEBUG)
    con_log_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_log_handler.setFormatter(formatter)
    con_log_handler.setFormatter(formatter)
    logger.addHandler(file_log_handler)
    if '--quiet' not in sys.argv:
        logger.addHandler(con_log_handler)
    main()