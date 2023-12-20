import os

from config import log
from config import BASE_DIR, FABRIC_TOOLS_CONFIGTXGEN, CUSTOM_CONFIGTX_YAML

# [TODO] Create a configtx.yaml generator that can be used to generate a configtx.yaml file
# based on the network configuration.


class Channel:
    def __init__(
        self,
            channel_name, channel_artifacts_dir,
            configtx_bin=FABRIC_TOOLS_CONFIGTXGEN,
            configtx_yaml=CUSTOM_CONFIGTX_YAML,
            configtx_yaml_profile="default",
    ):
        self.configtx = configtx_bin
        self.configtx_config = configtx_yaml
        self.configtx_config_profile = configtx_yaml_profile

        self.channel_name = channel_name
        self.channel_artifacts_dir = channel_artifacts_dir

        self.genesis_block = None

    def create_genesis_block(self):
        """Creates the genesis block for the channel"""
        # Create the destination directory if it does not exist
        if not os.path.exists(self.channel_artifacts_dir):
            os.makedirs(self.channel_artifacts_dir)
        
        # Create the genesis block
        cmd = \
            f"{self.configtx} " + \
            f"-outputBlock {self.channel_artifacts_dir}/genesis.block " + \
            f"-profile {self.configtx_config_profile} " + \
            f"-channelID {self.channel_name} " + \
            f"-configPath {os.path.dirname(self.configtx_config)} "
        log.info(
            f"Creating genesis block for channel {self.channel_name} with command: {cmd}")
        os.system(cmd)

        if os.path.exists(f"{self.channel_artifacts_dir}/genesis.block"):
            self.genesis_block = f"{self.channel_artifacts_dir}/genesis.block"
            log.info(f"Genesis block for channel {self.channel_name} created successfully")
        else:
            log.error(f"Genesis block for channel {self.channel_name} could not be created")
    
    def get_genesis_block_path(self):
        return self.genesis_block
    
    def inspect_genesis_block(self):
        """Reads the genesis block for the channel"""
        if not os.path.exists(f"{self.channel_artifacts_dir}/genesis.block"):
            log.error(f"Genesis block for channel {self.channel_name} could not be read")
            return
        cmd = \
            f"{self.configtx} " + \
            f"-inspectBlock {self.channel_artifacts_dir}/genesis.block"
        log.info(
            f"Inspecting genesis block for channel {self.channel_name} with command: {cmd}")
        os.system(cmd)


if __name__ == "__main__":
    # Create the channel
    channel = Channel(
        channel_name="nicola-channel",
        channel_artifacts_dir=os.path.join(BASE_DIR, "channel-artifacts"),
    )
    channel.create_genesis_block()
    channel.inspect_genesis_block()


