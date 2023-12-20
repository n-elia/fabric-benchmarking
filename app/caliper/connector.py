import json
import os
import shutil
import time
from pprint import pformat

import yaml
from config import (CALIPER_DIR, CALIPER_NETWORK_CONFIG_FILE, CALIPER_USER_DIR,
                    log)
from fabric.network import Container, FabricNetwork, FabricNetworkPeerOrg

CALIPER_DOCKER_IMAGE = "hyperledger/caliper:0.5.0"

class CaliperConnector:
    def __init__(self, fn:FabricNetwork, channel_name, chaincode_id, caliper_workspace_path: str = CALIPER_DIR, caliper_net_conf_file_path: str = CALIPER_NETWORK_CONFIG_FILE, caliper_user_path: str = CALIPER_USER_DIR):
        self.fn = fn
        self.workspace_path = caliper_workspace_path
        self.user_path = caliper_user_path
        # Create the user directory if it does not exist
        os.makedirs(self.user_path, exist_ok=True)

        self.c = Container(
            container_name="caliper",
            container_image=CALIPER_DOCKER_IMAGE,
            container_dcmd=f"launch manager",
            container_volumes=[
                f"{self.workspace_path}:/hyperledger/caliper/workspace"
            ],
            container_environment={
                'CALIPER_BIND_SUT': 'fabric:2.4',
                'CALIPER_BENCHCONFIG': 'benchmarks/default.yaml',
                'CALIPER_NETWORKCONFIG': 'networks/fabric/network.yaml',
                'NODE_OPTIONS': "--max-old-space-size=5120"
            },
            restart=False,
            # memory="10g", # Limit the available RAM
        )
        
        self.connection_profile_path = os.path.join(self.user_path, "connection_profile.json")
        self._generate_connection_profile()
        
        self.network = CaliperFabricNetwork(
            caliper_workspace_path=self.workspace_path,
            channel_name=channel_name,
            chaincode_id=chaincode_id,
            connection_profile_path=self.connection_profile_path,
            network_config_file_path=caliper_net_conf_file_path,
            fn=self.fn,
        )

        self.network.save_network_yaml()

    def _generate_connection_profile(self):
        cp = self.fn.get_connection_profile()
        log.debug(f"CaliperConnector: generated connection profile:\n{pformat(cp)}")
        
        # Store as JSON
        with open(self.connection_profile_path, "w") as f:
            json.dump(cp, f, indent=4)

    def start(self):
        self.c.start()

    def wait(self):
        while self.c.is_running():
            time.sleep(2)
    
    def stop(self):
        self.c.stop()
    
    def stop_and_remove_container(self):
        self.stop()
        self.c.remove()
    

class CaliperFabricNetwork:
    def __init__(self, caliper_workspace_path, channel_name, chaincode_id, connection_profile_path, network_config_file_path, fn: FabricNetwork):
        self.workspace_path = caliper_workspace_path
        self.channel_name = channel_name
        self.chaincode_id = chaincode_id
        self.connection_profile_path = connection_profile_path # Relative to the caliper workspace path
        self.network_config_file_path = network_config_file_path

        self.cfg = {}
        self._generate_base_network_yaml()

        for org in fn.peer_orgs:
            self._add_organization(org, self.connection_profile_path)

    def _generate_base_network_yaml(self):
        self.cfg["name"] = "Caliper benchmark"
        self.cfg["version"] = "2.0.0"

        self.cfg["caliper"] = dict()
        self.cfg["caliper"]["blockchain"] = "fabric"

        self.cfg["channels"] = []
        self.cfg["channels"].append(
            {
                "channelName": self.channel_name,
                "contracts": [
                    {
                        "id": self.chaincode_id,
                    }
                ]
            }
        )

        self.cfg["organizations"] = []
        
    def _add_organization(self, org: FabricNetworkPeerOrg, connection_profile_path):
        # By default, use the first peer's identity
        org_msp_id = org.ca.org_msp_id
        org_name = org.ca.org_name
        peer = org.get_peers()[0]

        user_name = peer.name
        user_tls_signcert_path = peer.get_tls_sign_cert_path()
        user_tls_private_key_path = peer.get_tls_key_path()

        # Create a subdirectory for this user, relative to the caliper workspace path
        user_dir = f"{self.workspace_path}/networks/fabric/user/{org_name}/{user_name}"
        os.makedirs(user_dir, exist_ok=True)

        # Copy the peer's certificates and keys to the user directory
        user_tls_signcert_path_rel_host = os.path.join(user_dir, "tls_signcert.pem")
        shutil.copyfile(user_tls_signcert_path, user_tls_signcert_path_rel_host)
        user_tls_private_key_path_rel_host = os.path.join(user_dir, "tls_key.pem")
        shutil.copyfile(user_tls_private_key_path, user_tls_private_key_path_rel_host)

        user_signcert_path_rel_host = os.path.join(user_dir, "signcert.pem")
        shutil.copyfile(peer.get_sign_cert_path(), user_signcert_path_rel_host)
        user_private_key_path_rel_host = os.path.join(user_dir, "key.pem")
        shutil.copyfile(peer.get_key_path(), user_private_key_path_rel_host)

        self.cfg["organizations"].append(
            {
                "mspid": org_msp_id,
                "identities": {
                    "certificates": [
                        {
                            "name": f"{user_name}",
                            "clientPrivateKey": {
                                "path": os.path.relpath(user_private_key_path_rel_host, self.workspace_path)
                                # "path": os.path.relpath(user_tls_private_key_path_rel_host, self.workspace_path)
                            },
                            "clientSignedCert": {
                                "path": os.path.relpath(user_signcert_path_rel_host, self.workspace_path)
                                # "path": os.path.relpath(user_tls_signcert_path_rel_host, self.workspace_path)
                            }
                        }
                    ],
                },
                "connectionProfile": {
                    "path": os.path.relpath(connection_profile_path, self.workspace_path),
                    "discover": True,
                },
            }
        )
        
    def save_network_yaml(self, dest: str = None):
        if dest is None:
            dest = self.network_config_file_path
        with open(dest, "w") as f:
            yaml.dump(self.cfg, f, default_flow_style=False)