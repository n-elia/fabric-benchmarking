import yaml
import os

def generate_equidistant_chunklengths_on_log_scale():
    chunk_lens = ()
    for e in range(100, 130, 1):
        exp = e / 10
        _ = 10 ** exp
        chunk_lens += int(_ * 1e-6 / 580),
    return chunk_lens

config = {
    "benchmark": {
        "description": "Caliper benchmark targeting HyperWatchdog.",
        "name": "bench_policy_gateway",
        "test": {
            "rounds": [
                {
                    "description": "Caliper benchmark targeting HyperWatchdog.",
                    "label": "Policy Gateway 208",
                    "rateControl": {
                        "opts": {"startingTps": 150, "transactionLoad": 300},
                        "type": "fixed-load",
                    },
                    # "txNumber": 1000,
                    # "trim": 200,
                    "txDuration": 180,
                    "workload": {
                        "arguments": {
                            "chaincodeID": "basic",
                            "chunkLen": 208,
                            "policyId": "signal_energy_policy_v1",
                        },
                        "module": "benchmarks/workloads/policy-gateway.js",
                    },
                },
            ],
            "workers": {"number": 1},
        },
    },
    "launcher": {
        "network": {},
        "fabric": {},
    },
}

# Different network config tuples
# (throughput, delay, jitter, loss)
net_configs = [
    # (None, None, None, None),
    (2920, 74, 39, 3),
]

# Different chunkLen values
chunk_lens = (10, 100, 500, 1000)
# chunk_lens = generate_equidistant_chunklengths_on_log_scale()

# Different Fabric configurations
# (n_orgs, n_peer_per_org, n_orderers, starting_port)
fabric_configs = [
    (2, 2, 3, 7160),
    (3, 2, 3, 7160),
    (4, 2, 3, 7160),
    (5, 2, 3, 7160),
    (6, 2, 3, 7160),
]

TARGET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs")
CONFIG_FILENAME_STRING = "exp_3{}.yaml"

if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR)

for net_config in net_configs:
    c = config
    c["launcher"]["network"] = {}
    c["launcher"]["fabric"] = {}

    filename_suffix = ""

    if net_config[0] is not None:
        c["launcher"]["network"]["throughput"] = net_config[0]
        filename_suffix += f"_thr_{net_config[0]}"
    if net_config[1] is not None:
        c["launcher"]["network"]["delay"] = net_config[1]
        filename_suffix += f"_del_{net_config[1]}"
    if net_config[2] is not None:
        c["launcher"]["network"]["jitter"] = net_config[2]
        filename_suffix += f"_jit_{net_config[2]}"
    if net_config[3] is not None:
        c["launcher"]["network"]["loss"] = net_config[3]
        filename_suffix += f"_pl_{net_config[3]}"

    for chunk_len in chunk_lens:
        c["benchmark"]["test"]["rounds"][0]["label"] = f"Policy Gateway {chunk_len}"

        c["benchmark"]["test"]["rounds"][0]["workload"]["arguments"][
            "chunkLen"
        ] = chunk_len
        filename_prefix_chunklen = f"_chunklen_{chunk_len}"

        for fabric_config in fabric_configs:
            c["launcher"]["fabric"]["n_orgs"] = fabric_config[0]
            c["launcher"]["fabric"]["n_peer_per_org"] = fabric_config[1]
            c["launcher"]["fabric"]["n_orderers"] = fabric_config[2]
            c["launcher"]["fabric"]["starting_port"] = fabric_config[3]
            filename_prefix_fabric = f"_orgs_{fabric_config[0]}_peers_{fabric_config[1]}_orderers_{fabric_config[2]}"

            filename = CONFIG_FILENAME_STRING.format(
                filename_prefix_chunklen + filename_prefix_fabric + filename_suffix
            )
            print(f"Writing {filename}...")

            with open(os.path.join(TARGET_DIR, filename), "w") as f:
                yaml.dump(c, f)
