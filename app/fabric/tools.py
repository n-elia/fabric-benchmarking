import yaml
from fabric.network import FabricNodeType


class PortGenerator:
    def __init__(self, start_port):
        self.start_port = start_port
        self.current_port = start_port

    def get_port(self):
        self.current_port += 1
        return self.current_port


def generate_rnd_fabric_topology(starting_port, n_orgs, n_peer_per_org, n_orderers):
    pg = PortGenerator(starting_port)
    net_def = []
    net_def.append((FabricNodeType.CERT_AUTHORITY, "tls.ca", pg.get_port()))
    for i in range(1, n_orgs + 1):
        org_name = f"org{i}"
        org_peers = []
        for j in range(1, n_peer_per_org + 1):
            org_peers.append((f"peer{j}.{org_name}.org", pg.get_port()))
        net_def.append(
            (
                FabricNodeType.PEER_CA,
                f"ca.{org_name}.org",
                f"{org_name}.org",
                pg.get_port(),
                org_peers,
            )
        )
    orderers = []
    for i in range(1, n_orderers + 1):
        orderers.append((f"orderer{i}.orderer.org", pg.get_port(), pg.get_port()))
    net_def.append(
        (
            FabricNodeType.ORDERER_CA,
            "ca.orderer.org",
            "orderer.org",
            pg.get_port(),
            orderers,
        )
    )
    return net_def


def generate_configtx_yaml(net_def, base_dir=None, out_filename=None):
    if base_dir is None:
        BASE_DIR = "tmp"
    else:
        BASE_DIR = base_dir

    if out_filename is None:
        CONFIGTX_LOCATION = "configtx.yaml"
    else:
        CONFIGTX_LOCATION = out_filename

    base_config = {
        "Profiles": {
            "default": {
                "Application": {
                    "Capabilities": {"V2_0": True},
                    "Organizations": [],
                    "Policies": {
                        "Admins": {
                            "Rule": "MAJORITY " "Admins",
                            "Type": "ImplicitMeta",
                        },
                        "Endorsement": {
                            "Rule": "AND(",
                            "Type": "Signature",
                        },
                        "LifecycleEndorsement": {
                            "Rule": "AND(",
                            "Type": "Signature",
                        },
                        "Readers": {"Rule": "ANY " "Readers", "Type": "ImplicitMeta"},
                        "Writers": {"Rule": "ANY " "Writers", "Type": "ImplicitMeta"},
                    },
                },
                "Capabilities": {"V2_0": True},
                "Orderer": {
                    "Addresses": [],
                    # BatchSize is the maximum size of a block
                    # "BatchSize": {
                    #     "AbsoluteMaxBytes": "20 " "MB",
                    #     "MaxMessageCount": 1000,
                    #     "PreferredMaxBytes": "4 " "MB",
                    # },
                    # BatchTimeout is the maximum time to wait before creating a new block
                    # "BatchTimeout": "4s",
                    "BatchSize": {
                        "AbsoluteMaxBytes": "10 " "MB",
                        "MaxMessageCount": 500,
                        "PreferredMaxBytes": "2 " "MB",
                    },
                    "BatchTimeout": "2s",
                    "Capabilities": {"V2_0": True},
                    "EtcdRaft": {
                        "Consenters": [],
                        "Options": {
                            "ElectionTick": 10,
                            "HeartbeatTick": 1,
                            "MaxInflightBlocks": 5,
                            "SnapshotIntervalSize": "16 " "MB",
                            "TickInterval": "500ms",
                        },
                    },
                    "MaxChannels": 0,
                    "OrdererType": "etcdraft",
                    "Organizations": [],
                    "Policies": {
                        "Admins": {
                            "Rule": "MAJORITY " "Admins",
                            "Type": "ImplicitMeta",
                        },
                        "BlockValidation": {
                            "Rule": "ANY " "Writers",
                            "Type": "ImplicitMeta",
                        },
                        "Readers": {"Rule": "ANY " "Readers", "Type": "ImplicitMeta"},
                        "Writers": {"Rule": "ANY " "Writers", "Type": "ImplicitMeta"},
                    },
                },
                "Policies": {
                    "Admins": {"Rule": "MAJORITY " "Admins", "Type": "ImplicitMeta"},
                    "Readers": {"Rule": "ANY Readers", "Type": "ImplicitMeta"},
                    "Writers": {"Rule": "ANY Writers", "Type": "ImplicitMeta"},
                },
            }
        }
    }

    for node in net_def:
        if node[0] == FabricNodeType.CERT_AUTHORITY:
            pass
        elif node[0] == FabricNodeType.PEER_CA:
            common_name, name, exposed_port, peers_list = node[1:]
            msp_id = name.title().replace(".", "") + "MSP"

            # Add the Peer Organization to the configtx.yaml
            base_config["Profiles"]["default"]["Application"]["Organizations"].append(
                {
                    "ID": msp_id,
                    "MSPDir": f"{BASE_DIR}/organizations/peerOrganizations/{name}/ca/msp",
                    "Name": name,
                    "Policies": {
                        "Admins": {
                            "Rule": f"OR('{msp_id}.admin')",
                            "Type": f"Signature",
                        },
                        "Readers": {
                            "Rule": f"OR('{msp_id}.member')",
                            "Type": f"Signature",
                        },
                        "Writers": {
                            "Rule": f"OR('{msp_id}.member')",
                            "Type": f"Signature",
                        },
                    },
                    "SkipAsForeign": False,
                    "AnchorPeers": [
                        {
                            "Host": peer[0],
                            "Port": peer[1],
                        }
                        for peer in peers_list
                    ],
                }
            )

            base_config["Profiles"]["default"]["Application"]["Policies"][
                "Endorsement"
            ]["Rule"] = (
                base_config["Profiles"]["default"]["Application"]["Policies"][
                    "Endorsement"
                ]["Rule"]
                # + f"'{msp_id}.admin', "
                + f"'{msp_id}.member', "
                # + f"'{msp_id}.peer'"
                # + ","
            )
            base_config["Profiles"]["default"]["Application"]["Policies"][
                "LifecycleEndorsement"
            ]["Rule"] = (
                base_config["Profiles"]["default"]["Application"]["Policies"][
                    "LifecycleEndorsement"
                ]["Rule"]
                # + f"'{msp_id}.admin', "
                + f"'{msp_id}.member', "
                # + f"'{msp_id}.peer'"
                # + ","
            )

        elif node[0] == FabricNodeType.ORDERER_CA:
            common_name, name, exposed_port, orderers_list = node[1:]
            msp_id = name.title().replace(".", "") + "MSP"

            # Add the Orderer Organization to the configtx.yaml
            base_config["Profiles"]["default"]["Orderer"]["Organizations"].append(
                {
                    "ID": msp_id,
                    "MSPDir": f"{BASE_DIR}/organizations/ordererOrganizations/{name}/ca/msp",
                    "Name": name,
                    "OrdererEndpoints": [
                        f"{orderer[0]}:{orderer[1]}" for orderer in orderers_list
                    ],
                    "Policies": {
                        "Admins": {
                            "Rule": f"OR('{msp_id}.admin')",
                            "Type": "Signature",
                        },
                        "Readers": {
                            "Rule": f"OR('{msp_id}.member')",
                            "Type": "Signature",
                        },
                        "Writers": {
                            "Rule": f"OR('{msp_id}.member')",
                            "Type": "Signature",
                        },
                    },
                    "SkipAsForeign": False,
                }
            )

            for orderer in orderers_list:
                base_config["Profiles"]["default"]["Orderer"]["EtcdRaft"][
                    "Consenters"
                ].append(
                    {
                        "ClientTLSCert": f"{BASE_DIR}/organizations/ordererOrganizations/{name}/orderers/{orderer[0]}/tls/signcerts/cert.pem",
                        "Host": orderer[0],
                        "Port": orderer[1],
                        "ServerTLSCert": f"{BASE_DIR}/organizations/ordererOrganizations/{name}/orderers/{orderer[0]}/tls/signcerts/cert.pem",
                    }
                )
                base_config["Profiles"]["default"]["Orderer"]["Addresses"].append(
                    f"{orderer[0]}:{orderer[1]}"
                )
        else:
            raise Exception("Unknown node type in network definition")

    base_config["Profiles"]["default"]["Application"]["Policies"]["Endorsement"][
        "Rule"
    ] = (
        base_config["Profiles"]["default"]["Application"]["Policies"]["Endorsement"][
            "Rule"
        ][:-2]
        + ")"
    )

    base_config["Profiles"]["default"]["Application"]["Policies"][
        "LifecycleEndorsement"
    ]["Rule"] = (
        base_config["Profiles"]["default"]["Application"]["Policies"][
            "LifecycleEndorsement"
        ]["Rule"][:-2]
        + ")"
    )

    # Write the configtx.yaml file
    with open(CONFIGTX_LOCATION, "w") as f:
        yaml.dump(base_config, f)


def generate_hosts_file(net_def, hosts_location="./hosts"):
    cn_list = []

    for node in net_def:
        if node[0] == FabricNodeType.CERT_AUTHORITY:
            # cn_list.append(f"{node[1]}:{node[2]}")
            cn_list.append(f"{node[1]}")

        elif node[0] == FabricNodeType.PEER_CA:
            common_name, name, exposed_port, peers_list = node[1:]
            # cn_list.append(f"{common_name}:{exposed_port}")
            cn_list.append(f"{common_name}")

            for peer in peers_list:
                # cn_list.append(f"{peer[0]}:{peer[1]}")
                cn_list.append(f"{peer[0]}")

        elif node[0] == FabricNodeType.ORDERER_CA:
            common_name, name, exposed_port, orderers_list = node[1:]
            # cn_list.append(f"{common_name}:{exposed_port}")
            cn_list.append(f"{common_name}")

            for orderer in orderers_list:
                # cn_list.append(f"{orderer[0]}:{orderer[1]}")
                cn_list.append(f"{orderer[0]}")

    base_str = "127.0.0.1 "
    output_str = base_str + " ".join(cn_list)

    print(output_str)
    print("add the above to your /etc/hosts file with:")
    print(f"sudo sh -c 'echo \"{output_str}\" >> /etc/hosts'")

    # Write the hosts file
    # with open(hosts_location, "w") as f:
    #     f.write(output_str)
