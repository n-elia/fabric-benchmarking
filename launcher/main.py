# This script is the main script for the launcher.
# It reads the yaml configurations from the `configs` folder.
# Then, for each configuration, it creates the coresponding yaml file into the caliper folder and runs the app.
# At the end of each run, it copies the results into the results folder. The result is the caliper report.
# Each caliper report will be renamed with the name of the corresponding configuration.

import os
import shutil
import time
import docker

import config as c

docker_client = docker.from_env()

# Important: implement your own clean_docker function if you don't want all containers to be stopped and removed
def clean_docker():
    # Stop and remove all the containers
    for c in docker_client.containers.list(all=True):
        c.stop()
        c.remove()
    
    # Prune docker volumes
    docker_client.volumes.prune()

# Directories of the app
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
APP_PATH = os.path.join(BASE_DIR, "app", "main.py")
# Check if the app exists
if not os.path.exists(APP_PATH):
    raise Exception("The app does not exist. Run the launcher from the root folder.")

# Directory to store the results
RESULTS_DIR = os.path.join(BASE_DIR, "launcher", "results")

# Directories of Caliper
CALI_CONFIG_DIR = os.path.join(BASE_DIR, "launcher", "caliper_configs")
CALI_DEFAULT_REPORT_PATH = os.path.join(BASE_DIR, "caliper", "workspace", "report.html")
CALI_DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "caliper", "workspace", "benchmarks", "default.yaml")

# Backup the default caliper config file
shutil.copyfile(CALI_DEFAULT_CONFIG_PATH, CALI_DEFAULT_CONFIG_PATH + ".bak")

# Directory that stores config files
LAUNCHER_CFG_DIR = os.path.join(BASE_DIR, "launcher", "configs")
if not os.path.exists(LAUNCHER_CFG_DIR):
    print("Config directory does not exist")
    exit(1)

# Initialize the config object to read the benchmarks config files
config = c.Config(LAUNCHER_CFG_DIR)
clean_docker()

while True:
    try:
        cfg = config.next()
        if cfg is None:
            break
            
        # print("Network config: ", cfg["launcher"]["network"])
        # print("Fabric config: ", cfg["launcher"]["fabric"])

        network_cfg = cfg["launcher"]["network"] if "network" in cfg["launcher"] else {}
        fabric_cfg = cfg["launcher"]["fabric"] if "fabric" in cfg["launcher"] else {}
        smart_contract_cfg = cfg["launcher"]["smart_contract"] if "smart_contract" in cfg["launcher"] else {}

        caliper_cfg_file = os.path.join(CALI_CONFIG_DIR, cfg["name"])
        c.config_dict_to_yaml(cfg["benchmark"], caliper_cfg_file)

        try:
            print("Running {}".format(cfg["name"]))
            # Copy the config file into the caliper folder (overwrite)
            os.system("rm -rf {}".format(CALI_DEFAULT_CONFIG_PATH))
            os.system("cp {} {}".format(os.path.join(caliper_cfg_file), CALI_DEFAULT_CONFIG_PATH))
            
            # Run the app
            cmd = f"python3 {APP_PATH} --not-interactive"
            if "max-throughput" in network_cfg and network_cfg["max-throughput"] is not None:
                cmd += f" -t {network_cfg['max-throughput']}"
            if "latency" in network_cfg and network_cfg["latency"] is not None:
                cmd += f" -d {network_cfg['delay']}"
            if "jitter" in network_cfg and network_cfg["jitter"] is not None:
                cmd += f" -j {network_cfg['jitter']}"
            if "loss" in network_cfg and network_cfg["loss"] is not None:
                cmd += f" -l {network_cfg['loss']}"

            if "n_orgs" in fabric_cfg and fabric_cfg["n_orgs"] is not None:
                cmd += f" --n-orgs {fabric_cfg['n_orgs']}"
            if "n_peer_per_org" in fabric_cfg and fabric_cfg["n_peer_per_org"] is not None:
                cmd += f" --n-peer-per-org {fabric_cfg['n_peer_per_org']}"
            if "n_orderers" in fabric_cfg and fabric_cfg["n_orderers"] is not None:
                cmd += f" --n-orderers {fabric_cfg['n_orderers']}"
            if "starting_port" in fabric_cfg and fabric_cfg["starting_port"] is not None:
                cmd += f" --starting-port {fabric_cfg['starting_port']}"
            
            if "name" in smart_contract_cfg and smart_contract_cfg["name"] is not None:
                cmd += f" --smart-contract-name {smart_contract_cfg['name']}"
            if "path" in smart_contract_cfg and smart_contract_cfg["path"] is not None:
                cmd += f" --smart-contract-path {smart_contract_cfg['path']}"
            if "version" in smart_contract_cfg and smart_contract_cfg["version"] is not None:
                cmd += f" --smart-contract-ver {smart_contract_cfg['version']}"
            
            print("Invoking command: ", cmd)
            os.system(cmd)

            # Copy the report into the results folder
            time.sleep(1)
            os.system("cp {} {}".format(CALI_DEFAULT_REPORT_PATH, os.path.join(RESULTS_DIR, cfg["name"] + ".html")))

            clean_docker()
        
        except KeyboardInterrupt:
            print("Keyboard interrupt detected. Exiting...")
            clean_docker()
            break
        
        except Exception as e:
            print("Error while running {}".format(cfg["name"]))
            print(e)
            clean_docker()
            break

    # Catch the Ctrl-C signal
    except KeyboardInterrupt:
        print("Keyboard interrupt detected. Exiting...")
        clean_docker()
        break

# Restore the default caliper config file
shutil.move(CALI_DEFAULT_CONFIG_PATH + ".bak", CALI_DEFAULT_CONFIG_PATH)

