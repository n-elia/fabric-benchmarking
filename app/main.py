import os
import time
import argparse

from fabric.network import FabricNetwork
from fabric.tools import generate_configtx_yaml, generate_hosts_file, generate_rnd_fabric_topology
from caliper.connector import CaliperConnector

from config import BASE_DIR, cleanup
from tools import PortGenerator

# Set to True to enable interactivity, i.e., wait for user input before executing each step
# Set to False to execute all steps without waiting for user input, e.g. when using the laucher
INTERACTIVITY = True

def interactive(f):
    """Wrapper that executes the function only if INTERACTIVITY is True"""
    def wrapper(*args, **kwargs):
        if INTERACTIVITY:
            return f(*args, **kwargs)
        else:
            return None
    return wrapper

@interactive
def pause(msg):
    return input(msg)

# Main
if __name__ == "__main__":
    # Take arguments from command line and store into a dictionary
    parser = argparse.ArgumentParser(prog="HyperBenchmarker", description="Deploy a Hyperledger Fabric Network, run a Chaincode and perform a benchmark.", add_help=True)
    parser.add_argument("--hosts", action="store_true", help="Generate the hosts file and exit")
    parser.add_argument("--interactive", action="store_true", help="Generate the hosts file and exit")
    parser.add_argument("--not-interactive", action="store_true", help="Generate the hosts file and exit")

    # Network parameters
    parser.add_argument("-t", "--throughput", type=int, help="Network: Max throughput in mbit/s")
    parser.add_argument("-d", "--delay", type=int, help="Network: Delay in ms")
    parser.add_argument("-j", "--jitter", type=int, help="Network: Jitter in ms")
    parser.add_argument("-l", "--loss", type=int, help="Network: Loss in percentage 0-100")

    # Fabric network parameters
    parser.add_argument("--n-orgs", type=int, help="Number of Fabric organizations")
    parser.add_argument("--n-peer-per-org", type=int, help="Number of Fabric peers per organization")
    parser.add_argument("--n-orderers", type=int, help="Number of Fabric orderers")
    parser.add_argument("--starting-port", type=int, help="Starting port for the Fabric network")

    # Target smart contract
    parser.add_argument("--smart-contract-name", type=str, help="Smart contract to deploy")
    parser.add_argument("--smart-contract-path", type=str, help="Path to the smart contract to deploy")
    parser.add_argument("--smart-contract-ver", type=str, help="Version of the smart contract to deploy")

    args = parser.parse_args()

    # Set interactivity (override default value if specified in the command line)
    if args.interactive:
        INTERACTIVITY = True
    elif args.not_interactive:
        INTERACTIVITY = False
        
    HOSTS_ONLY = args.hosts

    # Cleanup
    cleanup()
    # Create base directory if it does not exist
    os.makedirs(BASE_DIR, exist_ok=True)

    # Common TC parameters. No limits if the parameter is not specified
    common_tc = {
        # "throughput": 2920,  # mbit/s
        # "delay": 74,         # ms
        # "jitter": 39,        # ms
        # "loss": 3           # %
    }

    # Override common TC parameters with the ones specified in the command line
    if args.throughput:
        common_tc["throughput"] = args.throughput
    if args.delay:
        common_tc["delay"] = args.delay
    if args.jitter:
        common_tc["jitter"] = args.jitter
    if args.loss:
        common_tc["loss"] = args.loss
    
    # Apply TC only to the following hosts. Apply to all if None or empty list
    tc_filter = [
        # "peer1.org1.org",
        # "peer2.org1.org",
    ]

    # Definition of the Fabric Network
    starting_port = args.starting_port if args.starting_port else 7160
    n_orgs = args.n_orgs if args.n_orgs else 2
    n_peer_per_org = args.n_peer_per_org if args.n_peer_per_org else 2
    n_orderers = args.n_orderers if args.n_orderers else 1

    net_def = generate_rnd_fabric_topology(
        starting_port=starting_port,
        n_orgs=n_orgs,
        n_peer_per_org=n_peer_per_org,
        n_orderers=n_orderers
        )

    # Generate the configtx.yaml file and hosts file based on the network definition
    # Note: the configtx.yaml file is generated in the base directory because it will be
    #       used by the Fabric Network class to setup the network
    generate_configtx_yaml(net_def=net_def, base_dir=BASE_DIR, out_filename=os.path.join(BASE_DIR, "../configtx.yaml"))
    generate_hosts_file(net_def=net_def, hosts_location=os.path.join(BASE_DIR, "hosts"))

    # Wait for user to patch the hosts file
    pause("Patch the hosts file, then press any key to deploy the network...")
    if HOSTS_ONLY:
        exit(0)

    # Setup the Fabric Network
    fn = FabricNetwork(net_def, common_tc=common_tc, tc_filter=tc_filter)

    # Nodes
    fn.setup_tls_ca()
    fn.setup_peer_orgs()
    fn.setup_peers()
    fn.setup_orderer_orgs()
    fn.setup_orderers()

    # Channel
    fn.setup_channel()
    fn.join_orderers_to_channel()

    # Chaincode (Smart Contract)
    chaincode_name = args.smart_contract_name if args.smart_contract_name else "basic"
    chaincode_path = args.smart_contract_path if args.smart_contract_path else os.path.join(BASE_DIR, "..", "smartcontract", "hyper-watchdog", "chaincode-go")
    # chaincode_path = args.smart_contract_path if args.smart_contract_path else os.path.join(BASE_DIR, "..", "smartcontract", "asset-transfer-basic", "chaincode-go")
    chaincode_version = args.smart_contract_ver if args.smart_contract_ver else "1.0"

    # Package the chaincode and install it on all peers
    fn.package_chaincode(cc_source_path=chaincode_path, cc_name=chaincode_name, cc_version=chaincode_version)
    fn.install_chaincode()

    # Join peers to the channel and approve the chaincode definition
    fn.join_peers_to_channel()
    time.sleep(5)
    fn.approve_chaincode_definitions()
    time.sleep(3)

    # Invoke the chaincode (for testing purposes)
    # fn.invoke_chaincode(
    #     chaincode_cmd="{\"function\":\"CreateAsset\",\"Args\":[\"name\", \"Chevy\", \"2\", \"Red\", \"33\"]}",
    # )

    # Wait for user input to start the test
    key = pause("Press enter to start the test or C+enter to skip...")

    if key != "c":
        # Start the test with Caliper and wait for it to finish
        cali = CaliperConnector(
            fn=fn,
            channel_name="nicola-channel",
            chaincode_id=chaincode_name,
        )
        cali.start()
        cali.wait()

    # Wait for user input to teardown the network
    time.sleep(1)
    pause("Press any key to teardown the network...")

    # Teardown the Fabric Network
    fn.teardown()
    try:
        # Stop and remove the Caliper container
        cali.stop_and_remove_container()
    except:
        pass

    # Cleanup
    pause("Press any key to cleanup the environment, or CTRL+C to exit without cleaning ...")
    cleanup()
