import yaml
import os

config = {
    "name": "bench_policy_gateway",
    "description": "Caliper benchmark targeting HyperWatchdog.",
    "test": {
        "workers": {
            "number": 1
        },
        "rounds": [
            {
                "label": "Chunk Length 4165",
                "description": "Populates the ledger with 1500 entries.",
                "txNumber": 1500,
                "rateControl": {
                    "type": "fixed-feedback-rate",
                    "opts": {
                        "tps": 10,
                        "transactionLoad": 200,
                    },
                },
                "workload": {
                    "module": "benchmarks/workloads/policy-gateway.js",
                    "arguments": {
                        "chaincodeID": "basic",
                        "chunkLen": 4165,
                        "policyId": "signal_energy_policy_v1"
                    },
                },
            },
        ],
    }
}

chunk_lengths = (208, 417, 833, 1666, 4165)
tps_list = (5, 10, 20, 40, 80, 160)

TARGET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "caliper_configs")
CONFIG_FILENAME_STRING = "vm_06_thr_2920_tps_{}_chunklen_{}.yaml"

for chunk_length in chunk_lengths:
    for tps in tps_list:
        config["test"]["rounds"][0]["rateControl"]["opts"]["tps"] = tps
        config["test"]["rounds"][0]["label"] = f"Chunk Length {chunk_length} TPS {tps}"
        config["test"]["rounds"][0]["workload"]["arguments"]["chunkLen"] = chunk_length

        if not os.path.exists(TARGET_DIR):
            os.makedirs(TARGET_DIR)
        
        filename = CONFIG_FILENAME_STRING.format(tps, chunk_length)
        print(f"Writing {filename}...")

        with open(os.path.join(TARGET_DIR, filename) , "w") as f:
            yaml.dump(config, f)
