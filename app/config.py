import os
import shutil
import logging


CURR_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(CURR_DIR, "tmp")

# Please use a version that matches the Fabric CA container
FABRIC_CA_CLIENT = os.path.join(CURR_DIR, "../fabric/bin/fabric-ca-client")
# Please use a version that matches the Fabric orderer container
FABRIC_ORDERER_OSNADMIN = os.path.join(CURR_DIR, "../fabric/bin/osnadmin")
# Please use a version that includes tc (traffic control)
# FABRIC_CA_CONTAINER = "nelia/fabric-ca-tc:1.5.5"
FABRIC_CA_CONTAINER = "nelia/fabric-ca-tc:1.5.6"
# Please use a version that includes tc (traffic control)
# FABRIC_PEER_CONTAINER = "nelia/fabric-peer-tc:2.4.7"
FABRIC_PEER_CONTAINER = "nelia/fabric-peer-tc:2.4.9"
# Please use a version that includes tc (traffic control)
# FABRIC_ORDERER_CONTAINER = "nelia/fabric-orderer-tc:2.4.7"
FABRIC_ORDERER_CONTAINER = "nelia/fabric-orderer-tc:2.4.9"

DEFAULT_CORE_YAML = os.path.join(BASE_DIR, "../../fabric/config/core.yaml")
DEFAULT_ORDERER_YAML = os.path.join(BASE_DIR, "../../fabric/config/orderer.yaml")
DEFAULT_CONFIGTX_YAML = os.path.join(BASE_DIR, "../../fabric/config/configtx.yaml")

FABRIC_TOOLS_CONFIGTXGEN = os.path.join(CURR_DIR, "../fabric/bin/configtxgen")
FABRIC_TOOLS_PEER = os.path.join(CURR_DIR, "../fabric/bin/peer")
CUSTOM_CONFIGTX_YAML = os.path.join(CURR_DIR, "configtx.yaml")

CALIPER_DIR = os.path.join(CURR_DIR, "../caliper/workspace")
CALIPER_NETWORK_CONFIG_FILE = os.path.join(CALIPER_DIR, "networks/fabric/network.yaml")
CALIPER_USER_DIR = os.path.join(CALIPER_DIR, "networks/fabric/user")

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def export_env(key, value):
    """ Export environment variables. """
    os.environ[key] = value


def cleanup():
    """ Remove the base directory. """
    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)
        # os.rmdir(BASE_DIR)
        log.info("Removed directory: {}".format(BASE_DIR))
    else:
        log.debug("Directory does not exist: {}".format(BASE_DIR))
    
    if os.path.exists(CALIPER_USER_DIR):
        shutil.rmtree(CALIPER_USER_DIR)
        log.info("Removed directory: {}".format(CALIPER_USER_DIR))
    else:
        log.debug("Directory does not exist: {}".format(CALIPER_USER_DIR))

    if os.path.exists(CALIPER_NETWORK_CONFIG_FILE):
        os.remove(CALIPER_NETWORK_CONFIG_FILE)
        log.info("Removed file: {}".format(CALIPER_NETWORK_CONFIG_FILE))
    else:
        log.debug("File does not exist: {}".format(CALIPER_NETWORK_CONFIG_FILE))
