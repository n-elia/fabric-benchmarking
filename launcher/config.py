import os

import yaml

def config_dict_to_yaml(cfg, dest_filename):
    """ Convert a config dictionary to a yaml string.
    Saves the config to a file with the provided name."""
    with open(dest_filename, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)

class Config:
    def __init__(self, cfg_dir) -> None:
        # Parse all the config files in the config folder into a list of dictionaries
        self.configs = []
        for filename in os.listdir(cfg_dir):
            if not filename.endswith(".yaml") and not filename.endswith(".yml"):
                continue
            config_name = filename

            with open(os.path.join(cfg_dir, filename), "r") as f:
                config = yaml.safe_load(f)
                config["name"] = config_name
                self.configs.append(config)
    
    def __str__(self) -> str:
        return str(self.configs)
    
    def next(self):
        """ Return the next config in the list. """
        if len(self.configs) == 0:
            return None
        return self.configs.pop(0)

if __name__ == "__main__":
    MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    TMP_DIR = os.path.join(MODULE_DIR, "tmp")
    if not os.path.exists(TMP_DIR):
        os.makedirs(TMP_DIR)
    cfg_dir = os.path.join(MODULE_DIR, "configs")
    if not os.path.exists(cfg_dir):
        print("Config directory does not exist")
        exit(1)

    config = Config(cfg_dir)

    while True:
        cfg = config.next()
        if cfg is None:
            break
        
        print("LAUNCHER CONFIG: ", cfg["launcher"])
        # network_cfg = cfg["launcher"]["network"]
        # network_cfg["max-throughput"]
        # network_cfg["latency"]
        # network_cfg["jitter"]
        # network_cfg["loss"]
        
        print("CALIPER CONFIG: ", cfg["benchmark"])

        config_dict_to_yaml(cfg["benchmark"], os.path.join(TMP_DIR, cfg["name"]))

        input("Press enter to continue...")