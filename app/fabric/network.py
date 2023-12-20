import glob
import multiprocessing as mp
import os
import shutil
import subprocess
import time
from enum import Enum, auto
from typing import List

from config import (BASE_DIR, CURR_DIR, DEFAULT_CORE_YAML,
                    DEFAULT_ORDERER_YAML, FABRIC_CA_CLIENT,
                    FABRIC_CA_CONTAINER, FABRIC_ORDERER_CONTAINER,
                    FABRIC_ORDERER_OSNADMIN, FABRIC_PEER_CONTAINER,
                    FABRIC_TOOLS_PEER, log)
from container import Container
from fabric.chaincode import Chaincode, ChaincodeLanguage
from fabric.channels import Channel

MULTIPROCESSING_NUM_WORKERS = 8

# Convention used for storing the msp folders and crypto material:
# - All the material is stored into BASE_DIR
# - The 1st level subdirectories are: externalCAs, ordererOrganizations, peerOrganizations
# - The 2nd level subdirectories for ordererOrganizations and peerOrganizations are: ca, orderers, peers
# - The 2nd level subdirectories for externalCAs are: tlsCAs
# - The last levels described above contain the folders named with the common name of each identity, e.g. orderer.example.com, tls.ca, etc.
# - Each entity folder will eventually contain the msp and tls folders, and other folders to store crypto material.


def serialize_cert_from_path(cert_path):
    """ Serialize a certificate by reding it from a file path.
        The certificate will be returned as a single-line PEM string, with
        the header and footer and the newline characters."""
    with open(cert_path, "r") as f:
        cert = f.read()
    return cert


# Enum for certificate authority types
class CaType(Enum):
    PEER = auto()
    ORDERER = auto()
    TLS = auto()


class CertAuthority:
    def __init__(self,
                 exposed_port,
                 common_name,
                 admin_name,
                 admin_pass,
                 org_name=None,
                 container_tc_params=None,
                 ca_type: CaType = None,
                 tls_ca_cert=None,
                 ):
        """ Create a new certificate authority. """
        if (org_name is None) and (ca_type is not CaType.TLS):
            raise ValueError("org_name must be set for non-TLS CA")

        if ca_type is not CaType.TLS and tls_ca_cert is None:
            raise ValueError("tls_ca_cert must be set for non-TLS CA")

        # Type can be one of: "ordererOrg", "peerOrg", "tlsCA"
        if ca_type is CaType.PEER:
            self.home_dir = os.path.join(
                BASE_DIR, "organizations", "peerOrganizations", org_name, "ca")
            # Build MSP name from org name removing the dots, making it CamelCase and adding "MSP" at the end
            self.org_msp_id = org_name.title().replace(".", "") + "MSP"
        elif ca_type is CaType.ORDERER:
            self.home_dir = os.path.join(
                BASE_DIR, "organizations", "ordererOrganizations", org_name, "ca")
            # Build MSP name from org name removing the dots, making it CamelCase and adding "MSP" at the end
            self.org_msp_id = org_name.title().replace(".", "") + "MSP"
        elif ca_type is CaType.TLS:
            self.home_dir = os.path.join(
                BASE_DIR, "externalCAs", "tlsCAs", common_name)
        else:
            raise ValueError("Invalid CertAuthority type: {}".format(ca_type))

        self.exposed_port = exposed_port
        self.common_name = common_name
        self.org_name = org_name
        self.admin_name = admin_name
        self.admin_pass = admin_pass
        self.ca_type = ca_type
        self.is_tls_ca = self.ca_type is CaType.TLS
        self.c = Container(
            container_name=common_name,
            container_image=FABRIC_CA_CONTAINER,
            container_dcmd=f"fabric-ca-server start -d -b {admin_name}:{admin_pass} --port {exposed_port}",
            container_volumes=[
                f"{self.home_dir}:/tmp/hyperledger/fabric-ca"
            ],
            container_port_bindings={
                exposed_port: exposed_port
            },
            container_environment={
                'FABRIC_CA_SERVER_HOME': '/tmp/hyperledger/fabric-ca',
                'FABRIC_CA_SERVER_TLS_ENABLED': 'true',
                'FABRIC_CA_SERVER_CSR_CN': common_name,
                'FABRIC_CA_SERVER_CSR_HOSTS': f'0.0.0.0,127.0.0.1,{self.common_name}',
                'FABRIC_CA_SERVER_DEBUG': 'true'
            },
            tc_params=container_tc_params,
            user_uid=os.getuid(),
        )

        # Create home directory if it does not exist
        os.makedirs(self.home_dir, exist_ok=True)

        # Copy the TLS CA certificate to the CA's home folder
        if not self.is_tls_ca:
            shutil.copy(tls_ca_cert, os.path.join(
                self.home_dir, "tls-ca-cert.pem"))

            os.makedirs(os.path.join(self.home_dir, "msp",
                        "tlscacerts"), exist_ok=True)
            shutil.copy(tls_ca_cert, os.path.join(
                self.home_dir, "msp", "tlscacerts", "tls-ca-cert.pem"))

    def start_container(self):
        self.c.start()
        # Wait for the container to start and the CA to produce the certificate
        time.sleep(2)

        # Copy the self-signed CA certificate to the CA's cacerts folder
        # Note: this is necessary to update the msp folder of the CA
        self.add_cacert(os.path.join(self.home_dir, "ca-cert.pem"))

    def stop_container(self):
        self.c.stop()

    def rm_container(self):
        self.c.remove()

    def stop_and_rm_container(self):
        self.stop_container()
        self.rm_container()

    def get_cert_path(self):
        """Returns the path (on the host machine) to the CA certificate"""
        return f"{self.home_dir}/ca-cert.pem"

    def get_cert_path_rel(self):
        """Returns the path (relative to the CA's folder) to the CA certificate"""
        return "../ca-cert.pem"

    def get_admin_dir(self):
        """Returns the path (on the host machine) to the directory for storing the admin identity"""
        return f"{self.home_dir}/bootstrapAdmin"

    def get_admin_cert_path(self):
        """Returns the path (on the host machine) to the admin's certificate"""
        return f"{self.get_admin_dir()}/signcerts/cert.pem"

    def get_admin_cert_path_rel(self):
        """Returns the path (relative to the admin's folder) to the admin's certificate"""
        return "../signcerts/cert.pem"

    def get_admin_key_path(self):
        """Returns the path (on the host machine) to the admin's key"""
        return f"{self.get_admin_dir()}/keystore/key.pem"

    def enroll_bootstrap_admin(self):
        """Enrolls the admin identity using the bootstrap admin credentials"""
        # Note: the container address must be resolved to the host machine's address by the
        # host machine's DNS resolver. This is because the container is running in a separate
        # network namespace and does not have access to the host machine's DNS resolver.
        # To avoid having to manually add an entry to the host machine's /etc/hosts file,
        # we use localhost as the address, instead of self.common_name.

        # Note: the relative path to the certificate is relative to the home folder. Since
        # the home folder is set to the admin's folder, the path is relative to the admin's folder.
        os.system(
            f"{FABRIC_CA_CLIENT} enroll -d \
            --home {self.get_admin_dir()} \
            --tls.certfiles {self.get_cert_path_rel()} \
            -u https://{self.admin_name}:{self.admin_pass}@0.0.0.0:{self.exposed_port}"
        )

        # Rename the key file
        for f in glob.glob(f"{self.get_admin_dir()}/msp/keystore/*"):
            shutil.copy(f"{f}", f"{self.get_admin_dir()}/msp/keystore/key.pem")

    def enroll_identity(self, home_folder, org_ca_cert_relative_path, enroll_id, enroll_secret, hosts=None):
        """ Enrolls an identity using the credentials obtained after the registration.
        It uses the tls profile to enroll the identity if the CA is a TLS CA.

        :param home_folder: the absolute path to the folder where the identity's MSP will be stored
        :param org_ca_cert_relative_path: the path (relative to the selected identity's MSP folder) to the organization's CA certificate
        :param enroll_id: the enrollment ID of the identity
        :param enroll_secret: the enrollment secret of the identity
        """
        # Note: if the DNS is properly configured, change '0.0.0.0' to self.common_name
        cmd = f"{FABRIC_CA_CLIENT} enroll -d " + \
            f"-u \"https://{enroll_id}:{enroll_secret}@0.0.0.0:{self.exposed_port}\" " + \
            f"--home {home_folder} " + \
            f"--tls.certfiles \"{org_ca_cert_relative_path}\""

        # Note: we add '0.0.0.0' and `127.0.0.1` to the list of hosts that the CA certificate is valid for
        # because the CA certificate is generated with the common name as the host name. Since the
        # container is running in a separate network namespace, the host name is not resolvable.
        if self.is_tls_ca:
            cmd += f" --mspdir \"tls\" " + \
                f"--enrollment.profile tls " + \
                f"--csr.hosts 0.0.0.0,127.0.0.1{','+hosts if hosts else ''}"

        log.info(f"Enrolling admin identity with command: {cmd}")
        os.system(cmd)

        # Rename the key file
        if self.is_tls_ca:
            for f in glob.glob(f"{home_folder}/tls/keystore/*"):
                shutil.copy(f"{f}", f"{home_folder}/tls/keystore/key.pem")
        else:
            for f in glob.glob(f"{home_folder}/msp/keystore/*"):
                shutil.copy(f"{f}", f"{home_folder}/msp/keystore/key.pem")

        if self.is_tls_ca:
            log.info(f"Enrollment complete. The new key should appear in the MSP folder inside \
                {home_folder}. Listing of the MSP folder: \
                {os.listdir(home_folder + '/tls/keystore')}")
        else:
            log.info(f"Enrollment complete. The new key should appear in the MSP folder inside \
                    {home_folder}. Listing of the MSP folder: \
                    {os.listdir(home_folder + '/msp/signcerts')}")

    def register_identity_as_admin(self, username, password, identity_type):
        """Registers a new identity using the admin credentials.
        The new identity can be of type peer, orderer, client, user.
        """
        # Note: the certificate path is relative to the home folder. Since
        # the home folder is set to the admin's folder, the path is relative
        # to the admin's folder. Since, by design choice, all the users folders
        # are located in the same directory as the admin's folder, the relative
        # path of the certificate is the same for all users.
        log.debug(
            f"The admin of the certification authority with name {self.common_name} \
            is registering a new identity with name {username} and password {password}. "
        )

        # Note: this command is run against the localhost machine to avoid problems
        # with the container's domain name resolution.
        os.system(
            f"{FABRIC_CA_CLIENT} register -d \
                --home {self.get_admin_dir()} \
                --tls.certfiles {self.get_cert_path_rel()} \
                --id.name {username} \
                --id.secret {password} \
                --id.type {identity_type} \
                -u https://0.0.0.0:{self.exposed_port}"
        )

    def add_admin_cert(self, cert_path):
        """Adds the admin certificate to the CA's admincerts directory"""
        os.makedirs(f"{self.home_dir}/msp/admincerts", exist_ok=True)
        # Take the filename from the cert_path and use it as the admincert filename
        cert_filename = os.path.basename(cert_path)
        # Copy the admin certificate to the peer's admincerts directory
        shutil.copy(cert_path, os.path.join(
            self.home_dir, "msp", "admincerts", cert_filename))

    def add_cacert(self, cert_path, cert_filename=None):
        """Adds the CA certificate to the CA's cacerts directory"""
        os.makedirs(f"{self.home_dir}/msp/cacerts", exist_ok=True)
        # Take the filename from the cert_path and use it as the cacert filename
        if cert_filename is None:
            cert_filename = os.path.basename(cert_path)
        # Copy the CA certificate to the peer's cacerts directory
        shutil.copy2(cert_path, os.path.join(
            self.home_dir, "msp", "cacerts", cert_filename))


class Peer:
    """Represents a peer node"""

    def __init__(
        self,
        peer_name,
        exposed_port,
        org_name,
        org_msp_id,
        tls_ca_cert: str,
        org_ca_cert: str,
        container_tc_params,
        org_ca_enroll_id,
        org_ca_enroll_secret,
        tls_ca_enroll_id,
        tls_ca_enroll_secret,
        peer_gossip_broadcast_list=None,
        peer_gossip_ext_endpoint=None,
    ):
        self.name = peer_name
        self.exposed_port = exposed_port
        self.org_name = org_name
        self.org_msp_id = org_msp_id
        self.home_dir = os.path.join(
            BASE_DIR, "organizations", "peerOrganizations", org_name, "peers", peer_name)

        if peer_gossip_broadcast_list is None:
            peer_gossip_broadcast_list = ""
        if peer_gossip_ext_endpoint is None:
            # By default the peer is exposed to other orgs
            peer_gossip_ext_endpoint = f"{peer_name}:{exposed_port}"

        self.c = Container(
            container_name=peer_name,
            container_image=FABRIC_PEER_CONTAINER,
            container_dcmd=f"peer node start",
            container_volumes=[
                f"{self.home_dir}:/etc/hyperledger/fabric",
                f"/var/run/docker.sock:/var/run/docker.sock",
                # f"/var/run:/var/run",
            ],
            container_port_bindings={
                exposed_port: exposed_port
            },
            # alternatively, set FABRIC_CFG_PATH to /etc/hyperledger/fabric and put the config core.yaml
            # in the same folder
            container_environment={
                "FABRIC_LOGGING_SPEC": "grpc=debug:info",
                'CORE_VM_ENDPOINT': 'unix:///var/run/docker.sock',
                # Put the deployed chaincodes in the same network as the peers
                'CORE_VM_DOCKER_HOSTCONFIG_NETWORKMODE': 'fabric_network',
                # Peer configuration
                'CORE_PEER_TLS_ENABLED': 'true',
                'CORE_PEER_GOSSIP_USELEADERELECTION': 'true',
                'CORE_PEER_GOSSIP_ORGLEADER': 'false',
                # 'CORE_PEER_PROFILE_ENABLED': 'false',  # false in production
                'CORE_PEER_MSPCONFIGPATH': f"/etc/hyperledger/fabric/msp",

                'CORE_PEER_TLS_CERT_FILE': f"/etc/hyperledger/fabric/tls/signcerts/cert.pem",
                'CORE_PEER_TLS_KEY_FILE': f"/etc/hyperledger/fabric/tls/keystore/key.pem",
                'CORE_PEER_TLS_ROOTCERT_FILE': f"/etc/hyperledger/fabric/tls/tlscacerts/tlscacert.pem",

                # Enable the following to enable mutual TLS authentication between peers and clients
                # 'CORE_PEER_TLS_CLIENTAUTHREQUIRED': 'true',
                # 'CORE_PEER_TLS_CLIENTROOTCAS_FILES': f"/etc/hyperledger/fabric/tls/tlscacerts/tlscacert.pem",
                # 'CORE_PEER_TLS_CLIENTCERT_FILE': f"/etc/hyperledger/fabric/tls/signcerts/cert.pem",
                # 'CORE_PEER_TLS_CLIENTKEY_FILE': f"/etc/hyperledger/fabric/tls/keystore/key.pem",

                'CORE_CHAINCODE_LOGGING_LEVEL': 'INFO',
                'CORE_CHAINCODE_EXECUTETIMEOUT': '30s',

                'CORE_PEER_ID': peer_name,
                'CORE_PEER_ADDRESS': f"{peer_name}:{exposed_port}",
                'CORE_PEER_LISTENADDRESS': f"0.0.0.0:{exposed_port}",
                # 'CORE_PEER_CHAINCODEADDRESS': f"{container_name}:{exposed_port}",
                # 'CORE_PEER_CHAINCODELISTENADDRESS': f"{peer_name}:{exposed_port}",
                'CORE_PEER_GOSSIP_BOOTSTRAP': peer_gossip_broadcast_list,
                'CORE_PEER_GOSSIP_EXTERNALENDPOINT': peer_gossip_ext_endpoint,
                'CORE_PEER_LOCALMSPID': org_msp_id,

                'CORE_PEER_LIMITS_CONCURRENCY_GATEWAYSERVICE': '3500',
            },
            tc_params=container_tc_params,
            user_uid=os.getuid(),
            cpu_no=2, # Number of CPUs to allocate to the container
        )

        # Enrollment keys
        self.org_ca_enroll_id = org_ca_enroll_id
        self.org_ca_enroll_secret = org_ca_enroll_secret
        self.tls_ca_enroll_id = tls_ca_enroll_id
        self.tls_ca_enroll_secret = tls_ca_enroll_secret

        # Copy the organization CA certificate to the peer's home directory
        os.makedirs(f"{self.home_dir}/msp/cacerts", exist_ok=True)
        shutil.copy2(org_ca_cert, f"{self.home_dir}/msp/cacerts/cacert.pem")
        # Copy the TLS CA certificate to the peer's home directory
        os.makedirs(f"{self.home_dir}/msp/tlscacerts", exist_ok=True)
        os.makedirs(f"{self.home_dir}/tls/tlscacerts", exist_ok=True)
        shutil.copy2(
            tls_ca_cert, f"{self.home_dir}/msp/tlscacerts/tlscacert.pem")
        shutil.copy2(
            tls_ca_cert, f"{self.home_dir}/tls/tlscacerts/tlscacert.pem")

        # Create the peer's core.yaml file by copying the default one
        shutil.copy2(
            DEFAULT_CORE_YAML,
            os.path.join(self.home_dir, "core.yaml")
        )

    def start_container(self):
        self.c.start()
        time.sleep(0.5)

    def stop_container(self):
        self.c.stop()

    def rm_container(self):
        self.c.remove()

    def stop_and_rm_container(self):
        self.stop_container()
        self.rm_container()

    def get_ca_cert_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the organization's CA certificate"""
        return "msp/cacerts/cacert.pem"

    def get_ca_cert_path(self):
        """Returns the path to the organization's CA certificate"""
        return os.path.join(self.home_dir, self.get_ca_cert_path_rel())

    def get_sign_cert_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the organization's CA certificate"""
        return "msp/signcerts/cert.pem"

    def get_sign_cert_path(self):
        """Returns the path to the organization's CA certificate"""
        return os.path.join(self.home_dir, self.get_sign_cert_path_rel())

    def get_key_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the organization's CA certificate"""
        return "msp/keystore/key.pem"

    def get_key_path(self):
        """Returns the path to the organization's CA certificate"""
        return os.path.join(self.home_dir, self.get_key_path_rel())

    def get_tls_ca_cert_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the TLS CA certificate"""
        return "msp/tlscacerts/tlscacert.pem"

    def get_tls_ca_cert_path(self):
        """Returns the path to the TLS CA certificate"""
        return os.path.join(self.home_dir, self.get_tls_ca_cert_path_rel())

    def get_tls_sign_cert_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the certificate signed by the TLS CA"""
        return "tls/signcerts/cert.pem"

    def get_tls_sign_cert_path(self):
        """Returns the path to the certificate signed by the TLS CA"""
        return os.path.join(self.home_dir, self.get_tls_sign_cert_path_rel())

    def get_tls_key_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the TLS key"""
        return "tls/keystore/key.pem"

    def get_tls_key_path(self):
        """Returns the path to the TLS key"""
        return os.path.join(self.home_dir, self.get_tls_key_path_rel())

    def get_home_dir(self):
        """Returns the absolute path of the peer's home directory"""
        return self.home_dir

    def add_admin_cert(self, cert_path):
        """Adds the admin certificate to the peer's admincerts directory"""
        os.makedirs(f"{self.home_dir}/msp/admincerts", exist_ok=True)
        # Take the filename from the cert_path and use it as the admincert filename
        cert_filename = os.path.basename(cert_path)
        # Copy the admin certificate to the peer's admincerts directory
        shutil.copy2(cert_path, os.path.join(
            self.home_dir, "msp", "admincerts", cert_filename))

    def add_ca_cert(self, cert_path):
        """Adds the CA certificate to the peer's cacerts directory"""
        os.makedirs(f"{self.home_dir}/msp/cacerts", exist_ok=True)
        # Take the filename from the cert_path and use it as the cacert filename
        cert_filename = os.path.basename(cert_path)
        # Copy the CA certificate to the peer's cacerts directory
        shutil.copy2(cert_path, os.path.join(
            self.home_dir, "msp", "cacerts", cert_filename))

    def get_address(self):
        """Returns the address of the peer"""
        return f"{self.c.container_name}:{self.exposed_port}"

    def get_core_yaml_path(self):
        """Returns the path to the peer's core.yaml file"""
        return os.path.join(self.home_dir, "core.yaml")


class Orderer:
    """Represents an orderer node"""

    def __init__(
        self,
        orderer_name,
        exposed_port,
        exposed_admin_port,
        org_name,
        org_msp_id,
        tls_ca_cert: str,
        org_ca_cert: str,
        container_tc_params,
        org_ca_enroll_id: str,
        org_ca_enroll_secret: str,
        tls_ca_enroll_id: str,
        tls_ca_enroll_secret: str,
    ):
        self.name = orderer_name
        self.exposed_port = exposed_port
        self.exposed_admin_port = exposed_admin_port
        self.org_name = org_name
        self.org_msp_id = org_msp_id
        self.home_dir = os.path.join(
            BASE_DIR, "organizations", "ordererOrganizations", org_name, "orderers", orderer_name)

        self.c = Container(
            container_name=orderer_name,
            container_image=FABRIC_ORDERER_CONTAINER,
            container_dcmd=f"orderer start",
            container_volumes=[
                f"{self.home_dir}:/etc/hyperledger/fabric",
                # f"{os.path.join(self.home_dir, 'admin')}:/etc/hyperledger/fabric/admin",
            ],
            container_port_bindings={
                exposed_port: exposed_port,
                exposed_admin_port: exposed_admin_port
            },
            container_environment={
                "FABRIC_LOGGING_SPEC": "grpc=debug:info",
                "ORDERER_HOME": "/etc/hyperledger/fabric",
                "ORDERER_HOST": orderer_name,
                "ORDERER_GENERAL_LISTENADDRESS": "0.0.0.0",
                "ORDERER_GENERAL_LISTENPORT": f"{exposed_port}",
                # Bootstrap method set to none allows starting the orderer without providing the genesis block
                # i.e. allows the orderer to start without a system channel
                "ORDERER_GENERAL_BOOTSTRAPMETHOD": "none",
                # Allows the peer to join an application channel
                "ORDERER_CHANNELPARTICIPATION_ENABLED": "true",
                # "ORDERER_GENERAL_BOOTSTRAPMETHOD": "file",
                # "ORDERER_GENERAL_BOOTSTRAPFILE": "genesis.block",
                "ORDERER_GENERAL_LOCALMSPID": org_msp_id,
                "ORDERER_GENERAL_LOCALMSPDIR": "msp",
                "ORDERER_GENERAL_TLS_ENABLED": "true",
                "ORDERER_GENERAL_TLS_CERTIFICATE": "/etc/hyperledger/fabric/tls/signcerts/cert.pem",
                "ORDERER_GENERAL_TLS_PRIVATEKEY": "/etc/hyperledger/fabric/tls/keystore/key.pem",
                "ORDERER_GENERAL_TLS_ROOTCAS": "[/etc/hyperledger/fabric/tls/tlscacerts/tlscacert.pem]",
                "ORDERER_GENERAL_LOGLEVEL": "debug",
                "ORDERER_DEBUG_BROADCASTTRACEDIR": "data/logs",
                # The following section is used to configure the orderer admin identity
                "ORDERER_ADMIN_LISTENADDRESS": f"0.0.0.0:{exposed_admin_port}",
                "ORDERER_ADMIN_TLS_ENABLED": "true",
                "ORDERER_ADMIN_TLS_PRIVATEKEY": "/etc/hyperledger/fabric/tls/keystore/key.pem",
                "ORDERER_ADMIN_TLS_CERTIFICATE": "/etc/hyperledger/fabric/tls/signcerts/cert.pem",
                "ORDERER_ADMIN_TLS_CLIENTAUTHREQUIRED": "true",
                # Admin client TLS CA Root certificate
                "ORDERER_ADMIN_TLS_CLIENTROOTCAS": "[/etc/hyperledger/fabric/tls/tlscacerts/tlscacert.pem]",
            },
            tc_params=container_tc_params,
            user_uid=os.getuid(),
            cpu_no=2, # Number of CPUs to allocate to the container
        )

        # Enrollment keys
        self.org_ca_enroll_id = org_ca_enroll_id
        self.org_ca_enroll_secret = org_ca_enroll_secret
        self.tls_ca_enroll_id = tls_ca_enroll_id
        self.tls_ca_enroll_secret = tls_ca_enroll_secret

        # Copy the organization CA certificate to the orderer's home directory
        os.makedirs(f"{self.home_dir}/msp/cacerts", exist_ok=True)
        shutil.copy2(org_ca_cert, f"{self.home_dir}/msp/cacerts/cacert.pem")
        # Copy the TLS CA certificate to the orderer's home directory
        os.makedirs(f"{self.home_dir}/msp/tlscacerts", exist_ok=True)
        shutil.copy2(
            tls_ca_cert, f"{self.home_dir}/msp/tlscacerts/tlscacert.pem")
        os.makedirs(f"{self.home_dir}/tls/tlscacerts", exist_ok=True)
        shutil.copy2(
            tls_ca_cert, f"{self.home_dir}/tls/tlscacerts/tlscacert.pem")

        # Create the orderer's orderer.yaml file by copying the default one
        shutil.copy2(
            DEFAULT_ORDERER_YAML,
            os.path.join(self.home_dir, "orderer.yaml")
        )

    def get_admin_address(self):
        """Returns the address of the orderer's administation interface,
        formatted as <container_name>:<exposed_admin_port>"""
        return f"{self.c.container_name}:{self.exposed_admin_port}"

    def start_container(self):
        self.c.start()
        time.sleep(0.5)

    def stop_container(self):
        self.c.stop()

    def rm_container(self):
        self.c.remove()

    def stop_and_rm_container(self):
        self.stop_container()
        self.rm_container()

    def get_ca_cert_path(self):
        """Returns the path to the organization's CA certificate"""
        return os.path.join(self.home_dir, self.get_ca_cert_path_rel())

    def get_ca_cert_path_rel(self):
        """Returns the path (relative to the orderer's home folder) to the organization's CA certificate"""
        return "msp/cacerts/cacert.pem"

    def get_tls_ca_cert_path_rel(self):
        """Returns the path (relative to the orderer's home folder) to the TLS CA certificate"""
        return "msp/tlscacerts/tlscacert.pem"

    def get_home_dir(self):
        """Returns the absolute path of the orderer's home directory"""
        return self.home_dir

    def add_admin_cert(self, cert_path):
        """Adds the admin certificate to the orderer's admincerts directory"""
        os.makedirs(f"{self.home_dir}/msp/admincerts", exist_ok=True)
        # Take the filename from the cert_path and use it as the admincert filename
        cert_filename = os.path.basename(cert_path)
        # Copy the admin certificate to the peer's admincerts directory
        shutil.copy2(cert_path, os.path.join(
            self.home_dir, "msp", "admincerts", cert_filename))

    def add_ca_cert(self, cert_path):
        """Adds the CA certificate to the orderer's cacerts directory"""
        os.makedirs(f"{self.home_dir}/msp/cacerts", exist_ok=True)
        # Take the filename from the cert_path and use it as the admincert filename
        cert_filename = os.path.basename(cert_path)
        # Copy the admin certificate to the peer's admincerts directory
        shutil.copy2(cert_path, os.path.join(
            self.home_dir, "msp", "cacerts", cert_filename))

    def get_tls_ca_cert_path(self):
        """Returns the path to the TLS CA certificate"""
        return os.path.join(self.home_dir, self.get_tls_ca_cert_path_rel())

    def get_tls_signcert_path(self):
        """Returns the path to the TLS signcert"""
        return os.path.join(self.home_dir, "tls", "signcerts", "cert.pem")


class ClientType(Enum):
    """Represents the type of a client"""
    ADMIN = 1
    USER = 2


class OrgType(Enum):
    """Represents the type of an organization"""
    ORDERER = "ordererOrganizations"
    PEER = "peerOrganizations"


class Client:
    def __init__(
            self,
            client_type: ClientType, client_name: str,
            org_name: str, org_type: OrgType,
            org_ca_enrollment_id, org_ca_enrollment_secret,
            tls_ca_enrollment_id, tls_ca_enrollment_secret,
            ca_cert_path: str = None,
            tls_ca_cert_path: str = None,
    ):
        """Define a client (admin or user) for an organization

        Example:
            c = Client(
                client_type=ClientType.ADMIN,
                client_name="admin",
                org_name="org1.example.com",
                org_type=OrgType.PEER,
                org_ca_enrollment_id="admin",
                org_ca_enrollment_secret="adminpw",
                tls_ca_enrollment_id="admin",
                tls_ca_enrollment_secret="adminpw",
                )
        """
        self.client_type = client_type
        self.client_name = client_name
        self.org_name = org_name
        self.org_ca_enrollment_id = org_ca_enrollment_id
        self.org_ca_enrollment_secret = org_ca_enrollment_secret
        self.tls_ca_enrollment_id = tls_ca_enrollment_id
        self.tls_ca_enrollment_secret = tls_ca_enrollment_secret

        if client_type == ClientType.ADMIN:
            self.home_dir = os.path.join(
                BASE_DIR, "organizations", org_type.value, org_name, "admins", f"{client_name}@{org_name}")
        elif client_type == ClientType.USER:
            self.home_dir = os.path.join(
                BASE_DIR, "organizations", org_type.value, org_name, "users", f"{client_name}@{org_name}")
        else:
            raise ValueError("Invalid client type")

        # Create the home directory if it does not exist
        os.makedirs(self.home_dir, exist_ok=True)

        # Copy the TLS CA certificate to the client's home directory
        os.makedirs(f"{self.home_dir}/msp/cacerts", exist_ok=True)
        shutil.copy2(
            ca_cert_path, f"{self.home_dir}/msp/cacerts/cacert.pem")

        # Copy the organization CA certificate to the client's home directory
        os.makedirs(
            f"{self.home_dir}/msp/tlscacerts", exist_ok=True)
        shutil.copy2(
            tls_ca_cert_path, f"{self.home_dir}/msp/tlscacerts/tlscacert.pem")

        # Store the path to the private and public tls keys
        self._priv_tls_key_path = os.path.join(
            self.home_dir, "tls", "keystore", "key.pem")
        self._tls_signcert_path = os.path.join(
            self.home_dir, "tls", "signcerts", "cert.pem")

    def get_home_dir(self):
        """Returns the absolute path of the client's home directory"""
        return self.home_dir

    def get_ca_cert_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the organization's CA certificate"""
        return "msp/cacerts/cacert.pem"

    def get_tls_ca_cert_path_rel(self):
        """Returns the path (relative to the peer's home folder) to the TLS CA certificate"""
        return "msp/tlscacerts/tlscacert.pem"

    def get_signed_certificate(self):
        """Returns the path to the client's signed certificate"""
        # Rename cert.pem to signcert-{client_name}.pem
        if not os.path.exists(os.path.join(self.home_dir, f"msp/signcerts/signcert-{self.client_name}.pem")):
            os.rename(
                os.path.join(self.home_dir, "msp/signcerts/cert.pem"),
                os.path.join(
                    self.home_dir, f"msp/signcerts/signcert-{self.client_name}.pem")
            )
        return os.path.join(self.home_dir, f"msp/signcerts/signcert-{self.client_name}.pem")


class AdminClient(Client):
    def list_orderer_channels(self, orderer: Orderer):
        """List the channels that the orderer is a member of"""
        # Substitute `127.0.0.1:{orderer.self.exposed_admin_port}` with `orderer.get_admin_address()` if the DNS resolution is working
        cmd = f"{FABRIC_ORDERER_OSNADMIN} channel list " + \
              f"-o 127.0.0.1:{orderer.exposed_admin_port} " + \
              f"--ca-file {orderer.get_tls_ca_cert_path()} " + \
              f"--client-cert {self._tls_signcert_path} " + \
              f"--client-key {self._priv_tls_key_path} "
        log.info("Listing channels on orderer %s with command %s",
                 orderer.name, cmd)
        return os.system(cmd)

    def join_orderer_to_channel(self, orderer: Orderer, channel_name: str, channel_config_block_path: str):
        """Join the orderer to the specified channel"""
        # Substitute `127.0.0.1:{orderer.self.exposed_admin_port}` with `orderer.get_admin_address()` if the DNS resolution is working
        cmd = f"{FABRIC_ORDERER_OSNADMIN} channel join " + \
              f"--channelID {channel_name} " + \
              f"--config-block {channel_config_block_path} " + \
              f"-o {orderer.name}:{orderer.exposed_admin_port} " + \
              f"--ca-file {orderer.get_tls_ca_cert_path()} " + \
              f"--client-cert {self._tls_signcert_path} " + \
              f"--client-key {self._priv_tls_key_path} "
        log.info("Joining orderer %s to channel %s with command %s",
                 orderer.name, channel_name, cmd)
        return os.system(cmd)

    def _get_peer_tool_base_string(self, peer: Peer):
        """Returns the pre-configured base string for peer CLI commands"""
        cmd = ""
        # Use the target peer's home directory as the FABRIC_CFG_PATH to retrieve the core.yaml
        cmd += f"FABRIC_CFG_PATH={peer.get_home_dir()} "
        # In an environment that can resolve hostnames, use the peer's hostname instead of localhost
        cmd += f"CORE_PEER_ADDRESS=127.0.0.1:{peer.exposed_port} "
        # Use the admin MSP to perform the request
        cmd += f"CORE_PEER_MSPCONFIGPATH=\"{os.path.join(self.get_home_dir(), 'msp')}\" "
        # Override the default core.yaml configuration with the peer's one
        cmd += f"CORE_PEER_LOCALMSPID=\"{peer.org_msp_id}\" "
        cmd += f"CORE_PEER_TLS_ENABLED=true "
        cmd += f"CORE_PEER_TLS_ROOTCERT_FILE=\"{peer.get_tls_ca_cert_path()}\" "

        return cmd

    def join_peer_to_channel(self, peer: Peer, channel_config_block_path: str):
        """Join the peer to the specified channel"""
        cmd = self._get_peer_tool_base_string(peer)
        self._copy_signcert_to_admincerts()

        cmd += f"{FABRIC_TOOLS_PEER} channel join -b \"{channel_config_block_path}\""
        log.info("Joining peer %s to channel with command %s", peer.name, cmd)
        return os.system(cmd)

    def _copy_signcert_to_admincerts(self):
        """Copy the admin's signed certificate to the admin's admincerts folder.
        This is required to perform some kinds of requests with peer binary."""
        admincerts_path = os.path.join(
            self.get_home_dir(), "msp", "admincerts")
        admincert_path = os.path.join(
            admincerts_path, f"{self.client_name}.pem")
        # Check if the admicert already exists
        if os.path.exists(admincert_path):
            log.debug(
                f"Admincert {self.client_name}.pem already exists, skipping copy")
            return
        os.makedirs(admincerts_path, exist_ok=True)
        shutil.copyfile(
            self.get_signed_certificate(),
            os.path.join(admincerts_path, f"{self.client_name}.pem")
        )

    def query_installed_chaincodes(self, peer: Peer):
        """Query the peer for the list of installed chaincodes"""
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)

        cmd += f"{FABRIC_TOOLS_PEER} lifecycle chaincode queryinstalled"
        log.info(
            "Querying installed chaincodes on peer %s with command %s", peer.name, cmd)
        return os.system(cmd)

    def install_chaincode(self, peer: Peer, cc_package_path: str):
        """Install the chaincode package on the peer"""
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)

        cmd += f"{FABRIC_TOOLS_PEER} lifecycle chaincode install " + \
               f"{cc_package_path}"
        log.info("Installing chaincode on peer %s with command %s", peer.name, cmd)
        return os.system(cmd)

    def approve_chaincode_definition(self, peer: Peer, channel_ID: str,
                                     cc_package_id: str, cc_name: str, cc_version: str,
                                     cc_sequence: int, orderer: Orderer, signature_policy: str = None):
        """ Approve the chaincode definition on the peer """
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)
        # Note: in this command we have to specify the TLS CA of the orderer with
        # the --cafile option, otherwise the command fails because the client can't validate
        # the TLS certificate of the orderer.
        cmd += f"{FABRIC_TOOLS_PEER} lifecycle chaincode approveformyorg " + \
               f"--channelID {channel_ID} " + \
            f"--name {cc_name} " + \
            f"--version {cc_version} " + \
            f"--package-id {cc_package_id} " + \
            f"--sequence {cc_sequence} " + \
            f"-o {orderer.name}:{orderer.exposed_port} " + \
            f"--tls --cafile \"{orderer.get_tls_ca_cert_path()}\" "
        # f"--ordererTLSHostnameOverride {orderer.name}"
        if signature_policy:
            cmd += f"--signature-policy {signature_policy} "
        log.info(
            "Approving chaincode definition on peer %s with command %s", peer.name, cmd)
        return os.system(cmd)

    def check_chaincode_commit_readiness(self, peer: Peer, channel_ID: str,
                                         cc_package_id: str, cc_name: str, cc_version: str,
                                         cc_sequence: int, orderer: Orderer, signature_policy: str = None):
        """ Checks the readiness of the chaincode commit on the peer """
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)
        # Note: in this command we have to specify the TLS CA of the orderer with
        # the --cafile option, otherwise the command fails because the client can't validate
        # the TLS certificate of the orderer.
        cmd += f"{FABRIC_TOOLS_PEER} lifecycle chaincode checkcommitreadiness " + \
            f"--channelID {channel_ID} " + \
            f"--name {cc_name} " + \
            f"--version {cc_version} " + \
            f"--sequence {cc_sequence} " + \
            f"-o {orderer.name}:{orderer.exposed_port} " + \
            f"--tls --cafile \"{orderer.get_tls_ca_cert_path()}\" "
        # f"--ordererTLSHostnameOverride {orderer.name}"
        if signature_policy:
            cmd += f"--signature-policy {signature_policy} "

        log.info(
            "Checking chaincode definition readiness on peer %s with command %s", peer.name, cmd)
        return os.system(cmd)

    def commit_chaincode_definition(self, peer: Peer, channel_ID: str,
                                    cc_name: str, cc_version: str,
                                    cc_sequence: int, orderer: Orderer,
                                    signature_policy: str = None,
                                    additional_peers: List[Peer] = []):
        """ Commit the definition of the chaincode on the peer """
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)
        # Note: in this command we have to specify the TLS CA of the orderer with
        # the --cafile option, otherwise the command fails because the client can't validate
        # the TLS certificate of the orderer.
        cmd += f"{FABRIC_TOOLS_PEER} lifecycle chaincode commit " + \
            f"--channelID {channel_ID} " + \
            f"--name {cc_name} " + \
            f"--version {cc_version} " + \
            f"--sequence {cc_sequence} " + \
            f"-o {orderer.name}:{orderer.exposed_port} " + \
            f"--tls --cafile \"{orderer.get_tls_ca_cert_path()}\" "

        if signature_policy:
            cmd += f"--signature-policy {signature_policy} "

        if additional_peers:
            for p in additional_peers:
                cmd += f"--peerAddresses {p.name}:{p.exposed_port} " + \
                    f"--tlsRootCertFiles \"{p.get_tls_ca_cert_path()}\" "

        log.info(
            "Committing chaincode definition on peer %s with command %s", peer.name, cmd)
        return os.system(cmd)

    def invoke_chaincode(self, peer: Peer, channel_name: str, chaincode_name: str, chaincode_cmd: str):
        """ Invoke the chaincode on the peer """
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)

        cmd += f"{FABRIC_TOOLS_PEER} chaincode invoke " + \
            f"--tls --cafile \"{peer.get_tls_ca_cert_path()}\" " + \
            f"--peerAddresses 127.0.0.1:{peer.exposed_port} " + \
            f"--tlsRootCertFiles \"{peer.get_tls_ca_cert_path()}\" " + \
            f"-n {chaincode_name} " + \
            f"-C {channel_name} " + \
            f"-c \'{chaincode_cmd}\'"

        log.info("Invoking chaincode on peer %s with command %s", peer.name, cmd)
        return os.system(cmd)

    def read_chaincode_id(self, peer: Peer, cc_package_path: str):
        """ Read the chaincode ID from the package file """
        self._copy_signcert_to_admincerts()

        cmd = self._get_peer_tool_base_string(peer)

        cmd += f"{FABRIC_TOOLS_PEER} lifecycle chaincode calculatepackageid " + \
            f"{cc_package_path}"
        log.info("Reading the chaincode ID on peer %s with command %s",
                 peer.name, cmd)
        # return os.system(cmd)

        # Get the output of the command
        output = subprocess.check_output(cmd, shell=True)
        output = output.decode("utf-8")

        return output.strip()


class FabricNodeType(Enum):
    CERT_AUTHORITY = "cert_authority"
    PEER_CA = "peer_ca"
    ORDERER_CA = "orderer_ca"
    PEER = "peer"
    ORDERER = "orderer"


class FabricNetworkPeerOrg:
    def __init__(
        self,
            ca: CertAuthority,
            admin: AdminClient = None,
            peers_cfg=None,
    ) -> None:
        self.ca = ca
        self.admin = admin
        self.peers_cfg = peers_cfg
        self._peers: List[Peer] = []

    def add_peer(self, peer: Peer):
        print("Adding peer ", peer.name, "to org ", self.ca.org_name)
        self._peers.append(peer)

    def get_peers(self) -> List[Peer]:
        return self._peers

    def set_admin(self, admin: AdminClient):
        self.admin = admin


class FabricNetworkOrdererOrg:
    def __init__(
        self,
            ca: CertAuthority,
            admin: AdminClient = None,
            orderers_cfg=None,
    ) -> None:
        self.ca = ca
        self.admin = admin
        self.orderers_cfg = orderers_cfg
        self._orderers = []

    def add_orderer(self, orderer: Orderer):
        print("Adding orderer ", orderer.name, "to org ", self.ca.org_name)
        self._orderers.append(orderer)

    def set_admin(self, admin: AdminClient):
        self.admin = admin


class NetworkDefinition:
    def __init__(self, net_definition: List) -> None:
        # Parse the network definition
        self.tls_ca = None  # Should be only 1
        self.peer_cas = []
        self.orderer_cas = []

        for node in net_definition:
            if node[0] == FabricNodeType.CERT_AUTHORITY:
                self.tls_ca = node

            elif node[0] == FabricNodeType.PEER_CA:
                self.peer_cas.append(node)

            elif node[0] == FabricNodeType.ORDERER_CA:
                self.orderer_cas.append(node)

    def get_tls_ca(self):
        return self.tls_ca

    def get_peer_cas(self):
        # Return the list of peer CAs
        # Format: [ (FabricNodeType.PEER_CA, "ca.nicola.org", "nicola.org", 7055, [("peer1.nicola.org", 7051)]) ]
        return self.peer_cas

    def get_orderer_cas(self):
        # Return the list of orderer CAs
        # Format: [ (FabricNodeType.ORDERER_CA, "ca.orderer.org", "orderer.org", 7054, [("orderer1.orderer.org", 7050, 7053)]) ]
        return self.orderer_cas

# Helper functions for multiprocessing


def _start_all(p_list: list):
    for p in p_list:
        p.start()


def _wait_for_all(p_list: list):
    for p in p_list:
        p.join()


class FabricNetwork:
    def __init__(self, net_definition: List, common_tc=None, tc_filter=None) -> None:
        # Traffic control parameters
        if common_tc is None:
            self.common_tc = {
                "throughput": 0,  # mbit/s
                "delay": 0,         # ms
                "jitter": 0,         # ms
                "loss": 0            # %
            }
        else:
            self.common_tc = common_tc

        if tc_filter is None:
            self.tc_filter = []
        else:
            self.tc_filter = tc_filter

        self.netdef = NetworkDefinition(net_definition)

        self.peer_orgs: List[FabricNetworkPeerOrg] = []
        self.orderer_orgs: List[FabricNetworkOrdererOrg] = []

    def setup_tls_ca(self):
        cfg = self.netdef.get_tls_ca()

        # Setup TLS CA
        self.tls_ca = CertAuthority(
            exposed_port=cfg[2],
            common_name=cfg[1],
            admin_name="admin" + cfg[1],
            admin_pass="admin" + cfg[1] + "pw",
            # container_tc_params=self.common_tc.copy(), # Disable traffic control for TLS CA
            ca_type=CaType.TLS
        )

        # Start the TLS CA container
        log.info("FabricNetwork: Starting TLS CA container...")
        self.tls_ca.start_container()

        # Enroll the admin identity using the bootstrap admin credentials
        log.info("FabricNetwork: Enrolling TLS CA's bootstrap admin identity...")
        self.tls_ca.enroll_bootstrap_admin()

    def setup_peer_orgs(self):
        cfg = self.netdef.get_peer_cas()

        # Load the Peer Organizations from the network definition
        for node in cfg:
            self.peer_orgs.append(
                FabricNetworkPeerOrg(
                    ca=CertAuthority(
                        exposed_port=node[3],
                        common_name=node[1],
                        org_name=node[2],
                        admin_name="admin." + node[2],
                        admin_pass="admin." + node[2] + "pw",
                        # container_tc_params=self.common_tc.copy(), # Disable traffic control for TLS CA
                        ca_type=CaType.PEER,
                        tls_ca_cert=self.tls_ca.get_cert_path(),
                    ),
                    peers_cfg=node[4],
                )
            )

        # Setup the Admin
        for org in self.peer_orgs:
            # Start the Peer CA container
            log.info(
                "FabricNetwork: Starting Peer CA container with name: " + org.ca.common_name + "...")
            org.ca.start_container()

            # Enroll the admin identity using the bootstrap admin credentials
            log.info(
                "FabricNetwork: Enrolling Peer CA's bootstrap admin identity for " + org.ca.common_name + "...")
            org.ca.enroll_bootstrap_admin()

            # Setup the admin of the current Peer Organization
            log.info(
                "FabricNetwork: Setting up the admin of Peer Organization " + org.ca.org_name + "...")
            org.set_admin(
                AdminClient(
                    client_name="admin." + org.ca.org_name,
                    client_type=ClientType.ADMIN,
                    org_name=org.ca.org_name,
                    org_type=OrgType.PEER,
                    org_ca_enrollment_id="admin" + org.ca.org_name,
                    org_ca_enrollment_secret="admin" + org.ca.org_name + "pw",
                    tls_ca_enrollment_id="admin" + org.ca.org_name,
                    tls_ca_enrollment_secret="admin" + org.ca.org_name + "pw",
                    ca_cert_path=org.ca.get_cert_path(),
                    tls_ca_cert_path=self.tls_ca.get_cert_path(),
                )
            )

            # Register the admin identity into the Peer CA
            log.info(
                "FabricNetwork: Registering admin identity " + org.admin.client_name + " into Peer CA " + org.ca.common_name + "...")
            org.ca.register_identity_as_admin(
                org.admin.org_ca_enrollment_id,
                org.admin.org_ca_enrollment_secret,
                "admin"
            )

            # Enroll the admin identity into the Peer CA
            log.info(
                "FabricNetwork: Enrolling admin identity " + org.admin.client_name + " into Peer CA " + org.ca.common_name + "...")
            org.ca.enroll_identity(
                home_folder=org.admin.get_home_dir(),
                org_ca_cert_relative_path=org.admin.get_ca_cert_path_rel(),
                enroll_id=org.admin.org_ca_enrollment_id,
                enroll_secret=org.admin.org_ca_enrollment_secret
            )

            # Since Organizational Units are not used, we must place this certificate into peers' and CA's msp directories, under the admincerts folder
            log.info(
                "FabricNetwork: Placing admin identity's certificate into Peer CA's and peers' MSP directories...")
            org.ca.add_admin_cert(org.admin.get_signed_certificate())

            # Register the admin identity into the TLS CA
            log.info(
                "FabricNetwork: Registering admin identity " + org.admin.client_name + " into TLS CA " + self.tls_ca.common_name + "...")
            self.tls_ca.register_identity_as_admin(
                org.admin.tls_ca_enrollment_id,
                org.admin.tls_ca_enrollment_secret,
                "admin"
            )

            # Enroll the admin identity into the TLS CA
            log.info(
                "FabricNetwork: Enrolling admin identity " + org.admin.client_name + " into TLS CA " + self.tls_ca.common_name + "...")
            self.tls_ca.enroll_identity(
                home_folder=org.admin.get_home_dir(),
                org_ca_cert_relative_path=org.admin.get_tls_ca_cert_path_rel(),
                enroll_id=org.admin.tls_ca_enrollment_id,
                enroll_secret=org.admin.tls_ca_enrollment_secret
            )

    def setup_peers(self):
        # Setup the peers of the Peer Organizations
        peer_gossip_all_orgs_endpoints = []
        for org in self.peer_orgs:
            for peer in org.peers_cfg:
                peer_gossip_all_orgs_endpoints.append(f"{peer[0]}:{peer[1]}")
        pool = mp.Pool(processes=MULTIPROCESSING_NUM_WORKERS)
        for curr_org in self.peer_orgs:
            # `peers` will be a list of tuples (peer_name, exposed_port)
            log.info(
                "FabricNetwork: Setting up the peers " + str(curr_org.peers_cfg) + " belonging to Peer CA " + curr_org.ca.common_name + "...")

            # Build the peer gossip broadcast list using the peer list of the current organization
            peer_gossip_broadcast_list_curr_org = [
                f"{peer[0]}:{peer[1]}" for peer in curr_org.peers_cfg]
            # Build the peer gossip external endpoints using the peer list of the other organizations
            peer_gossip_external_endpoints_curr_org = peer_gossip_all_orgs_endpoints.copy()
            [peer_gossip_external_endpoints_curr_org.remove(
                p) for p in peer_gossip_broadcast_list_curr_org]

            for peer in curr_org.peers_cfg:
                # Register the peer into the current Peer CA
                log.info("FabricNetwork: Registering peer identity " +
                         peer[0] + " into Peer CA " + curr_org.ca.common_name + "...")
                curr_org.ca.register_identity_as_admin(
                    peer[0],         # Enrollment username
                    peer[0] + "-pw",  # Enrollment password
                    "peer"
                )

                # Register the peer into the TLS CA
                log.info("FabricNetwork: Registering peer identity " +
                         peer[0] + " into TLS CA " + self.tls_ca.common_name + "...")
                self.tls_ca.register_identity_as_admin(
                    peer[0],         # Enrollment username
                    peer[0] + "-pw",  # Enrollment password
                    "peer"
                )

                # The peer gossip broadcast list is the list of all the peers in the organization, except the current one
                peer_gossip_broadcast_list = peer_gossip_broadcast_list_curr_org.copy()
                peer_gossip_broadcast_list.remove(f"{peer[0]}:{peer[1]}")
                log.info("Peer gossip broadcast list: %s",
                         peer_gossip_broadcast_list)

                # Build the peer object
                curr_peer = Peer(
                    peer_name=peer[0],
                    exposed_port=peer[1],
                    # common_name="peer1.nicola.org",
                    org_name=curr_org.ca.org_name,
                    org_msp_id=curr_org.ca.org_msp_id,
                    tls_ca_cert=self.tls_ca.get_cert_path(),
                    org_ca_cert=curr_org.ca.get_cert_path(),
                    container_tc_params=self.common_tc.copy(
                    ) if peer[0] in self.tc_filter else None,
                    org_ca_enroll_id=peer[0],
                    org_ca_enroll_secret=peer[0] + "-pw",
                    tls_ca_enroll_id=peer[0],
                    tls_ca_enroll_secret=peer[0] + "-pw",
                    # Format: space-separated list of <peer_name>:<port>
                    peer_gossip_broadcast_list=' '.join(
                        peer_gossip_broadcast_list),
                )

                # Enroll the peer identity using the Peer CA
                log.info("FabricNetwork: Enrolling peer " +
                         peer[0] + "'s identity against Peer CA " + curr_org.ca.common_name + "...")
                curr_org.ca.enroll_identity(
                    curr_peer.get_home_dir(),
                    curr_peer.get_ca_cert_path_rel(),
                    enroll_id=curr_peer.org_ca_enroll_id,
                    enroll_secret=curr_peer.org_ca_enroll_secret
                )

                # Enroll the peer identity using the TLS CA
                log.info("FabricNetwork: Enrolling peer " +
                         peer[0] + "'s identity against TLS CA " + self.tls_ca.common_name + "...")
                self.tls_ca.enroll_identity(
                    curr_peer.get_home_dir(),
                    curr_peer.get_tls_ca_cert_path_rel(),
                    enroll_id=curr_peer.tls_ca_enroll_id,
                    enroll_secret=curr_peer.tls_ca_enroll_secret,
                    hosts=peer[0]
                )

                # Since Organizational Units are not used, we must place the admin certificate into peers' admincerts directory
                log.info(
                    "FabricNetwork: Placing admin identity's certificate into peer's MSP directory...")
                curr_peer.add_admin_cert(
                    curr_org.admin.get_signed_certificate())

                # Start the peer
                log.info("FabricNetwork: Starting peer " + peer[0] + "...")
                pool.apply_async(curr_peer.start_container)
                # curr_peer.start_container()

                curr_org.add_peer(curr_peer)

        pool.close()
        pool.join()

    def setup_orderer_orgs(self):
        cfg = self.netdef.get_orderer_cas()

        # Load the Orderer Organizations from the network definition file
        for node in cfg:
            self.orderer_orgs.append(
                FabricNetworkOrdererOrg(
                    ca=CertAuthority(
                        exposed_port=node[3],
                        common_name=node[1],
                        org_name=node[2],
                        admin_name="admin." + node[2],
                        admin_pass="admin." + node[2] + "pw",
                        # container_tc_params=self.common_tc.copy(), # Disable traffic control for TLS CA
                        ca_type=CaType.ORDERER,
                        tls_ca_cert=self.tls_ca.get_cert_path(),
                    ),
                    orderers_cfg=node[4],
                )
            )

        # Setup the Orderer Organizations
        for org in self.orderer_orgs:
            # Start the Orderer Ca container
            log.info("FabricNetwork: Starting Orderer CA " +
                     org.ca.common_name + "...")
            org.ca.start_container()

            # Enroll the bootstrap admin identity
            log.info("FabricNetwork: Enrolling bootstrap admin identity for Orderer CA " +
                     org.ca.common_name + "...")
            org.ca.enroll_bootstrap_admin()

            # Setup an admin user for this Orderer Organization
            log.info(
                "FabricNetwork: Setting up the admin of Orderer Organization " + org.ca.org_name + "...")
            org.set_admin(
                AdminClient(
                    client_name="admin." + org.ca.org_name,
                    client_type=ClientType.ADMIN,
                    org_name=org.ca.org_name,
                    org_type=OrgType.ORDERER,
                    org_ca_enrollment_id="admin" + org.ca.org_name,
                    org_ca_enrollment_secret="admin" + org.ca.org_name + "pw",
                    tls_ca_enrollment_id="admin" + org.ca.org_name,
                    tls_ca_enrollment_secret="admin" + org.ca.org_name + "pw",
                    ca_cert_path=org.ca.get_cert_path(),
                    tls_ca_cert_path=self.tls_ca.get_cert_path(),
                )
            )

            # Register the admin identity into the Orderer CA
            log.info("FabricNetwork: Registering admin identity " +
                     org.admin.client_name + " into Orderer CA " + org.ca.common_name + "...")
            org.ca.register_identity_as_admin(
                org.admin.org_ca_enrollment_id,         # Enrollment username
                org.admin.org_ca_enrollment_secret,  # Enrollment password
                "admin"
            )

            # Enroll the admin identity into the Orderer CA
            log.info("FabricNetwork: Enrolling admin identity " +
                     org.admin.client_name + " into Orderer CA " + org.ca.common_name + "...")
            org.ca.enroll_identity(
                home_folder=org.admin.get_home_dir(),
                org_ca_cert_relative_path=org.admin.get_ca_cert_path_rel(),
                enroll_id=org.admin.org_ca_enrollment_id,
                enroll_secret=org.admin.org_ca_enrollment_secret
            )

            # Since Organizational Units are not used, we must place the admin certificate into peers' admincerts directory
            log.info(
                "FabricNetwork: Placing admin identity's certificate into Orderer Organization's MSP directory...")
            org.ca.add_admin_cert(org.admin.get_signed_certificate())

            # Register the admin identity into the TLS CA
            log.info("FabricNetwork: Registering admin identity " +
                     org.admin.client_name + " into TLS CA " + self.tls_ca.common_name + "...")
            self.tls_ca.register_identity_as_admin(
                org.admin.tls_ca_enrollment_id,         # Enrollment username
                org.admin.tls_ca_enrollment_secret,  # Enrollment password
                "admin"
            )

            # Enroll the admin identity into the TLS CA
            log.info("FabricNetwork: Enrolling admin identity " +
                     org.admin.client_name + " into TLS CA " + self.tls_ca.common_name + "...")
            self.tls_ca.enroll_identity(
                home_folder=org.admin.get_home_dir(),
                org_ca_cert_relative_path=org.admin.get_tls_ca_cert_path_rel(),
                enroll_id=org.admin.tls_ca_enrollment_id,
                enroll_secret=org.admin.tls_ca_enrollment_secret
            )

    def setup_orderers(self):
        pool = mp.Pool(processes=MULTIPROCESSING_NUM_WORKERS)

        for curr_org in self.orderer_orgs:
            # Setup the orderers of the current Orderer CA
            for orderer in curr_org.orderers_cfg:
                # Register the orderer into the current Orderer CA
                log.info("FabricNetwork: Registering orderer identity " +
                         orderer[0] + " into Orderer CA " + curr_org.ca.common_name + "...")
                curr_org.ca.register_identity_as_admin(
                    orderer[0],         # Enrollment username
                    orderer[0] + "-pw",  # Enrollment password
                    "orderer"
                )

                # Register the orderer into the TLS CA
                log.info("FabricNetwork: Registering orderer identity " +
                         orderer[0] + " into TLS CA " + self.tls_ca.common_name + "...")
                self.tls_ca.register_identity_as_admin(
                    orderer[0],         # Enrollment username
                    orderer[0] + "-pw",  # Enrollment password
                    "orderer"
                )

                # Build the orderer object
                o = Orderer(
                    orderer_name=orderer[0],
                    exposed_port=orderer[1],
                    exposed_admin_port=orderer[2],
                    org_name=curr_org.ca.org_name,
                    org_msp_id=curr_org.ca.org_msp_id,
                    tls_ca_cert=self.tls_ca.get_cert_path(),
                    org_ca_cert=curr_org.ca.get_cert_path(),
                    container_tc_params=self.common_tc.copy(
                    ) if orderer[0] in self.tc_filter else None,
                    org_ca_enroll_id=orderer[0],
                    org_ca_enroll_secret=orderer[0] + "-pw",
                    tls_ca_enroll_id=orderer[0],
                    tls_ca_enroll_secret=orderer[0] + "-pw"
                )
                curr_org.add_orderer(o)

                # Enroll the orderer identity using the Orderer CA
                log.info("FabricNetwork: Enrolling orderer " +
                         orderer[0] + "'s identity against Orderer CA " + curr_org.ca.common_name + "...")
                curr_org.ca.enroll_identity(
                    o.get_home_dir(),
                    o.get_ca_cert_path_rel(),
                    enroll_id=o.org_ca_enroll_id,
                    enroll_secret=o.org_ca_enroll_secret,
                    hosts=o.name
                )

                # Enroll the orderer identity using the TLS CA
                log.info("FabricNetwork: Enrolling orderer " +
                         orderer[0] + "'s identity against TLS CA " + self.tls_ca.common_name + "...")
                self.tls_ca.enroll_identity(
                    home_folder=o.get_home_dir(),
                    org_ca_cert_relative_path=o.get_tls_ca_cert_path_rel(),
                    enroll_id=o.tls_ca_enroll_id,
                    enroll_secret=o.tls_ca_enroll_secret,
                    hosts=o.name
                )

                # Since Organizational Units are not used, we must place the admin certificate into orderers' admincerts directory
                log.info(
                    "FabricNetwork: Placing admin identity's certificate into orderer's MSP directory...")
                o.add_admin_cert(curr_org.admin.get_signed_certificate())

                # Start the orderer
                log.info("FabricNetwork: Starting orderer " +
                         orderer[0] + "...")
                pool.apply_async(o.start_container)
                # o.start_container()

        pool.close()
        pool.join()

    def setup_channel(self):
        # Create the channel
        self.channel = Channel(
            channel_name="nicola-channel",
            channel_artifacts_dir=os.path.join(BASE_DIR, "channel-artifacts"),
        )
        log.info("FabricNetwork: Creating channel " +
                 self.channel.channel_name + "...")
        self.channel.create_genesis_block()

    def join_orderers_to_channel(self):
        # Join the orderers to the channel
        for org in self.orderer_orgs:
            for orderer in org._orderers:
                log.info("FabricNetwork: Joining orderer " +
                         orderer.name + " to channel " + self.channel.channel_name + "...")
                org.admin.join_orderer_to_channel(
                    orderer=orderer,
                    channel_name=self.channel.channel_name,
                    channel_config_block_path=self.channel.get_genesis_block_path()
                )

    def package_chaincode(self,
                          cc_source_path=None,
                          cc_name=None,
                          cc_version=None,
                          ):
        # TODO: Add support for externally defined chaincode
        # Chaincode path
        if cc_source_path is None:
            cc_source_path = os.path.join(
                CURR_DIR, "asset-transfer-basic", "chaincode-go")

        # Chaincode name and version
        if cc_name is None:
            cc_name = "asset-transfer-basic"
        if cc_version is None:
            cc_version = "1.0"

        cc_label = "{}-{}".format(cc_name, cc_version)

        # Create the chaincode
        self.cc = Chaincode(
            cc_name=cc_name,
            cc_version=cc_version,
            cc_source_path=cc_source_path,
            cc_lang=ChaincodeLanguage.GOLANG,
            cc_label=cc_label,
        )

        # Package the chaincode
        log.info("FabricNetwork: Packaging chaincode...")
        self.cc_package_path = self.cc.package()
        log.info(f"Chaincode packaged in: {self.cc_package_path}")

    def install_chaincode(self):
        for org in self.peer_orgs:
            peers = org.get_peers()

            for peer in peers:
                # Install the chaincode on the peer
                log.info("FabricNetwork: Installing chaincode on peer " +
                         peer.name + "belonging to organization " + org.ca.org_name + "...")
                org.admin.query_installed_chaincodes(peer=peer)
                org.admin.install_chaincode(
                    peer=peer,
                    cc_package_path=self.cc_package_path,
                )

                # Print the chaincodes installed on peer
                org.admin.query_installed_chaincodes(peer)

    def join_peers_to_channel(self):
        # Join the peers to the channel
        for org in self.peer_orgs:
            for peer in org.get_peers():
                log.info("FabricNetwork: Joining peer " +
                         peer.name + " to channel " + self.channel.channel_name + "...")
                org.admin.join_peer_to_channel(
                    peer=peer,
                    channel_config_block_path=self.channel.get_genesis_block_path()
                )

    def get_signature_policy(self):
        # Return None if you want to use the default signature policy
        # sp = '\"AND('
        # for org in self.peer_orgs:
        #     sp += f"\'{org.ca.org_msp_id}.member\', "
        # sp = sp[:-2] + ")\""  # Remove the last comma and close the string
        # return sp
        return None

    def approve_chaincode_definitions(self):
        for org in self.peer_orgs:
            cc_seq = 1

            for peer in org.get_peers():
                # Get the installed chaincode package id
                cc_id = org.admin.read_chaincode_id(
                    peer=peer,
                    cc_package_path=self.cc_package_path,
                )
                log.info("FabricNetwork: Chaincode installed on peer " +
                         peer.name + " with package id " + cc_id + ".")

                # Approve the chaincode definition
                log.info("FabricNetwork: Approving chaincode definition on peer " +
                         peer.name + "...")
                org.admin.approve_chaincode_definition(
                    peer=peer,
                    channel_ID=self.channel.channel_name,
                    cc_package_id=cc_id,
                    cc_name=self.cc.cc_name,
                    cc_version=self.cc.cc_version,
                    cc_sequence=1,
                    orderer=self.orderer_orgs[0]._orderers[0],
                    signature_policy=self.get_signature_policy(),
                )

                # It is sufficient to approve the chaincode definition on one peer
                break

        # Create a list with 1 peer per organization to commit the chaincode definition
        # Note: this is needed when the endorsement policy requires the approval of all the organizations
        endorsing_peers = []
        for org in self.peer_orgs:
            for peer in org.get_peers():
                endorsing_peers.append(peer)
                break
        
        cc_seq = 1

        for org in self.peer_orgs:
            for peer in org.get_peers():
                # Get the installed chaincode package id
                cc_id = org.admin.read_chaincode_id(
                    peer=peer,
                    cc_package_path=self.cc_package_path,
                )
                log.info("FabricNetwork: Chaincode installed on peer " +
                         peer.name + " with package id " + cc_id + ".")

                # Check if the chaincode definition is approved
                # Note: we don't interpret the output of the command, we just print it for debugging purposes
                log.info("FabricNetwork: Checking if chaincode definition is approved on peer " +
                         peer.name + "...")
                org.admin.check_chaincode_commit_readiness(
                    peer=peer,
                    channel_ID=self.channel.channel_name,
                    cc_package_id=cc_id,
                    cc_name=self.cc.cc_name,
                    cc_version=self.cc.cc_version,
                    cc_sequence=cc_seq,
                    orderer=self.orderer_orgs[0]._orderers[0],
                    signature_policy=self.get_signature_policy(),
                )

                # Commit the chaincode definition
                log.info("FabricNetwork: Committing chaincode definition on peer " +
                         peer.name + "...")
                org.admin.commit_chaincode_definition(
                    peer=peer,
                    channel_ID=self.channel.channel_name,
                    cc_name=self.cc.cc_name,
                    cc_version=self.cc.cc_version,
                    cc_sequence=cc_seq,
                    orderer=self.orderer_orgs[0]._orderers[0],
                    signature_policy=self.get_signature_policy(),
                    additional_peers=endorsing_peers
                )

                break

            # The chaincode definition must be committed once per channel
            break

    def invoke_chaincode(self, chaincode_cmd: str):
        # Invoke the chaincode using the admin of the first peer org
        self.peer_orgs[0].admin.invoke_chaincode(
            peer=self.peer_orgs[0].get_peers()[0],
            channel_name=self.channel.channel_name,
            chaincode_name=self.cc.cc_name,
            chaincode_cmd=chaincode_cmd,
            # chaincode_cmd="{\"function\":\"CreateAsset\",\"Args\":[\"name\", \"Chevy\", \"2\", \"Red\", \"33\"]}"
        )

    def teardown(self):
        pool = mp.Pool(processes=MULTIPROCESSING_NUM_WORKERS)

        # Stop and remove the TLS CA
        pool.apply_async(self.tls_ca.stop_and_rm_container)

        # Stop and remove the Orderer CAs and Orderers
        for org in self.orderer_orgs:
            pool.apply_async(org.ca.stop_and_rm_container)

            for orderer in org._orderers:
                pool.apply_async(orderer.stop_and_rm_container)

        # Stop and remove the Peer CAs and Peers
        for org in self.peer_orgs:
            pool.apply_async(org.ca.stop_and_rm_container)

            for peer in org.get_peers():
                pool.apply_async(peer.stop_and_rm_container)

        pool.close()
        pool.join()

    def get_connection_profile(self):
        conn_profile = {
            "name": "fabric-network",
            "version": "1.0.0",
            "organizations": {
                # Add the Peer Orgs in the form:
                # "my.org": {
                #     "mspid": "myOrgMSP",
                #     "peers": [
                #         "peer1.my.org"
                #     ],
                #     "certificateAuthorities": [
                #         "ca.my.org"
                #     ]
                # }
            },
            "peers": {
                # Add the Peers in the form:
                # "peer1.my.org": {
                #     "url": "grpcs://peer1.my.org:7053",
                #     "tlsCACerts": {
                #         "pem": "-----BEGIN CERTIFICATE-----\ ... CERTIFICATE-----\n"
                #     },
                #     "grpcOptions": {
                #         "ssl-target-name-override": "peer1.my.org",
                #         "hostnameOverride": "peer1.my.org"
                #     }
                # }
            },
            "certificateAuthorities": {
                # Add the CAs in the form:
                # "ca.my.org": {
                #     "url": "https://ca.my.org:7054",
                #     "caName": "ca.my.org",
                #     "tlsCACerts": {
                #         "pem": "-----BEGIN CERTIFICATE-----\ ... CERTIFICATE-----\n"
                #     },
                #     "httpOptions": {
                #         "verify": false
                #     }
                # }
            },
        }

        # Add the Peer Orgs
        for org in self.peer_orgs:
            conn_profile["organizations"][org.ca.org_name] = {
                "mspid": org.ca.org_msp_id,
                "peers": [peer.name for peer in org.get_peers()],
                "certificateAuthorities": [
                    org.ca.common_name
                ]
            }

        # Add the Peers
        for org in self.peer_orgs:
            for peer in org.get_peers():
                conn_profile["peers"][peer.name] = {
                    "url": f"grpcs://{peer.name}:{peer.exposed_port}",
                    "tlsCACerts": {
                        "pem": serialize_cert_from_path(peer.get_tls_ca_cert_path())
                    },
                    "grpcOptions": {
                        "ssl-target-name-override": peer.name,
                        "hostnameOverride": peer.name
                    }
                }

        # Add the CAs
        for org in self.peer_orgs:
            if org.ca.common_name not in conn_profile["certificateAuthorities"]:
                conn_profile["certificateAuthorities"][org.ca.common_name] = {
                    "url": f"https://{org.ca.common_name}:{org.ca.exposed_port}",
                    "caName": org.ca.common_name,
                    "tlsCACerts": {
                        "pem": serialize_cert_from_path(org.ca.get_cert_path())
                    },
                    "httpOptions": {
                        "verify": False
                    }
                }

        return conn_profile
