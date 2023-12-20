from enum import Enum
from time import sleep
import os
import shutil

from config import log
from config import BASE_DIR, CURR_DIR, FABRIC_TOOLS_PEER, CUSTOM_CONFIGTX_YAML, DEFAULT_CORE_YAML


class ChaincodeLanguage(Enum):
    GOLANG = "golang"
    JAVA = "java"
    NODE = "node"


class Chaincode:
    def __init__(
        self,
            cc_name,
            cc_version,
            cc_artifacts_dir=os.path.join(BASE_DIR, "chaincode-artifacts"),
            cc_source_path: str = None,
            cc_label=None,
            peer_bin=FABRIC_TOOLS_PEER,
            # core_yaml=CUSTOM_CONFIGTX_YAML,
            core_yaml=DEFAULT_CORE_YAML,
            cc_lang: ChaincodeLanguage = None,
    ):
        if cc_source_path is None:
            raise ValueError("cc_source_dir is required")
        if cc_lang is None:
            raise ValueError("cc_lang is required")
        self.cc_name = cc_name
        self.cc_version = cc_version
        self.cc_artifacts_dir = cc_artifacts_dir
        self.cc_source_path = cc_source_path
        self.cc_label = cc_label
        self.peer_bin = peer_bin
        self.cc_lang = cc_lang.value

        if cc_label is None:
            self.cc_label = f"{self.cc_name}-{self.cc_version}"

        # Copy the provided core.yaml file to the base directory (this is needed to run the `peer` CLI)
        self.core_yaml = core_yaml
        
        self.cc_package_path = None

    def package(self):
        """Packages the chaincode"""
        # Create the destination directory if it does not exist
        if not os.path.exists(self.cc_artifacts_dir):
            os.makedirs(self.cc_artifacts_dir)

        # Copy the default core.yaml file to the base directory (this is needed to run the `peer` CLI)
        core_yaml_dest = os.path.join(CURR_DIR, "../core.yaml")
        log.debug(f"Copying the core.yaml to the current path {core_yaml_dest}")
        shutil.copyfile(self.core_yaml, core_yaml_dest)
        sleep(0.1)
        
        # Package the chaincode
        cc_filename = f"{self.cc_name}.tar.gz"
        cc_package_path = os.path.join(self.cc_artifacts_dir, cc_filename)
        cmd = \
            f"{self.peer_bin} lifecycle chaincode package " + \
            f"{cc_package_path} " + \
            f"--path {self.cc_source_path} " + \
            f"--lang {self.cc_lang} " + \
            f"--label {self.cc_label} "
        log.info(f"Packaging chaincode {self.cc_name} with command: {cmd}")
        os.system(cmd)

        if os.path.exists(os.path.join(self.cc_artifacts_dir, cc_filename)):
            log.info(f"Chaincode {self.cc_name} packaged successfully into {cc_filename}")
        else:
            log.error(f"Chaincode {self.cc_name} could not be packaged")

        # Remove the default core.yaml file from the base directory
        log.debug(f"Deleting core.yaml file from the current path {core_yaml_dest}")
        os.remove(core_yaml_dest)

        self.cc_package_path = cc_package_path
        return cc_package_path
    
    def get_package_path(self):
        """Returns the path to the chaincode package"""
        if self.cc_package_path is None:
            raise ValueError("Chaincode has not been packaged yet")
        return self.cc_package_path

if __name__ == "__main__":
    # Create the chaincode
    cc = Chaincode(
        cc_name="asset-transfer-basic",
        cc_version="1.0",
        cc_source_path=os.path.join(CURR_DIR, "asset-transfer-basic", "chaincode-go"),
        cc_lang=ChaincodeLanguage.GOLANG,
    )
    # Package the chaincode
    cc.package()



