import docker
import yaml
import os

from config import log, BASE_DIR
from typing import List, Dict

# Docker client
docker_client = docker.from_env() # Default Docker context

# docker_socket_path = "/home/ubi/.docker/desktop/docker.sock"  # Docker Desktop context
# docker_socket_protocol = "unix://"
# docker_socket = docker_socket_protocol + docker_socket_path
# docker_client = docker.DockerClient(
#     base_url=docker_socket
# )

class Container:
    def __init__(self,
                 container_name: str,
                 container_image: str,
                 container_dcmd: str,
                 container_volumes: List[str],
                 container_port_bindings: Dict = None,
                 container_environment: Dict = None,
                 tc_params: Dict = None,
                 restart: bool = True,
                 memory: str = None,
                 user_uid: int = None,
                 cpu_no: int = None,
                 ):
        """ Create a new container

        :param container_name: Name of the container
        :type container_name: str
        :param container_image: Image to use for the container
        :type container_image: str
        :param container_dcmd: Command to run in the container
        :type container_dcmd: str
        :param container_volumes: Volumes to mount in the container. Example: ["/tmp/hyperledger:/tmp/hyperledger"]
        :type container_volumes: list
        :param container_port_bindings: Port bindings for the container. Example: {7054: 7054}
        :type container_port_bindings: dict
        :param container_environment: Environment variables for the container. Example: {"FABRIC_CA_SERVER_HOME": "/tmp/hyperledger/fabric-ca/crypto"}
        :type container_environment: dict
        :param tc_params: Traffic control parameters, dict with keys "throughput", "delay", "jitter", "loss". Units: mbit, ms, ms, %. Example: {"throughput": 1000, "delay": 0, "jitter": 0, "loss": 0}.
        :type tc_params: dict
        :param restart: Whether to restart the container on failure
        :type restart: bool
        :param memory: Memory limit for the container. Example: "1g"
        :type memory: str
        :param user_uid: UID of the user to run the container as
        :type user_uid: int
        :param cpu_no: Number of CPUs to allocate to the container. Example: 2
        :type cpu_no: int
        """
        self.container_name = container_name
        self.container_image = container_image
        self.container_dcmd = container_dcmd
        self.container_volumes = container_volumes
        if container_port_bindings is None:
            container_port_bindings = {}
        self.container_port_bindings = container_port_bindings
        if container_environment is None:
            container_environment = {}
        self.container_environment = container_environment
        self.tc_params = tc_params
        self.docker_network = "fabric_network"
        self.restart = restart
        self.memory = memory
        self.user_uid = user_uid
        self.cpu_no = cpu_no

    def start(self):
        # Check if the network exists
        try:
            docker_client.networks.get(self.docker_network)
        except docker.errors.NotFound:
            log.info("Creating network")
            docker_client.networks.create(self.docker_network, driver="bridge")
        
        container_settings = {
            "image": self.container_image,
            "name": self.container_name,
            "command": self.container_dcmd,
            "volumes": self.container_volumes,
            "ports": self.container_port_bindings,
            "environment": self.container_environment,
            "detach": True,
            "cap_add": ["NET_ADMIN"],
            "network": self.docker_network,
            # network_mode: "bridge",
        }

        if self.restart:
            container_settings["restart_policy"] = {"Name": "unless-stopped"}
        
        if self.memory is not None:
            container_settings["mem_limit"] = self.memory

        if self.user_uid is not None:
            container_settings["user"] = self.user_uid
        
        if self.cpu_no is not None:
            container_settings["nano_cpus"] = int(self.cpu_no * 1e9)
        
        log.debug("Starting container with settings: {}".format(container_settings))

        container = docker_client.containers.run(
            **container_settings
        )

        # Dump the container settings into a docker-compose file
        docker_compose = {
            "version": "2",
            "services": {
                self.container_name: {
                    "container_name": self.container_name,
                    "image": self.container_image,
                    "command": self.container_dcmd,
                    "volumes": self.container_volumes,
                    "ports": [f"{k}:{v}" for k,v in zip(self.container_port_bindings.keys(), self.container_port_bindings.values())],
                    "environment": self.container_environment,
                    "cap_add": ["NET_ADMIN"],
                    "networks": [self.docker_network],
                }
            },
            "networks": {
                self.docker_network: {
                    "external": True
                }
            }
        }

        # Create the compose folder if it does not exist
        compose_path = os.path.join(BASE_DIR, "compose")
        os.makedirs(os.path.join(compose_path, f"{self.container_name}"), exist_ok=True)
        with open(os.path.join(compose_path, f"{self.container_name}/docker-compose.yml"), "w") as f:
            f.write(yaml.dump(docker_compose))

        if self.tc_params is not None:
            self.traffic_control_enable(**self.tc_params)
        else:
            log.info(f"Traffic control not enabled for container {self.container_name}")

    def stop(self):
        container = docker_client.containers.get(self.container_name)
        container.stop()

    def remove(self):
        container = docker_client.containers.get(self.container_name)
        container.remove()

    def exec(self, cmd):
        container = docker_client.containers.get(self.container_name)
        return container.exec_run(cmd)

    def traffic_control_enable(self, throughput=1000000, delay=0, jitter=0, loss=0):
        # https://www.excentis.com/blog/use-linux-traffic-control-as-impairment-node-in-a-test-environment-part-2/
        # https://netbeez.net/blog/how-to-use-the-linux-traffic-control/
        # tc qdisc show
        # tc qdisc show dev eth0
        # tc qdisc del dev eth0 root
        if delay == 0:
            # tc netem works best with throughput specified. Using 1000Gbit is equivalent to disabling throttle.
            cmd = f"tc qdisc add dev eth0 root netem rate {throughput}mbit delay 0ms 0ms loss {loss}%"
        else:
            cmd = f"tc qdisc add dev eth0 root netem rate {throughput}mbit delay {delay}ms {jitter}ms distribution normal loss {loss}%"
        log.info(f"Enabling traffic control for container {self.container_name} with command: {cmd}")
        self.exec(cmd)


    # def traffic_control_enable(self, throughput=100000, delay=0, jitter=0, loss=0):
    #     """ Enable traffic control on the container's eth0 interface. 
    #         Default values are set to 0. """
    #     # https://www.excentis.com/blog/use-linux-traffic-control-as-impairment-node-in-a-test-environment-part-2/
        
    #     if throughput == 0 and delay == 0 and jitter == 0 and loss == 0:
    #         log.info(f"Traffic control not enabled for container {self.container_name}")
    #         return

    #     # Base command
    #     cmd = "tc qdisc add dev eth0 root netem"

    #     if jitter != 0 and delay == 0:
    #         raise ValueError("Cannot set jitter without delay")
        
    #     if throughput != 0:
    #         cmd += f" rate {throughput}mbit"
    #     if delay != 0:
    #         cmd += f" delay {delay}ms"
    #     if jitter != 0:
    #         cmd += f" {jitter}ms distribution normal"
    #     if loss != 0:
    #         cmd += f" loss {loss}%"

    #     log.info(f"Enabling traffic control for container {self.container_name} with command: {cmd}")
    #     self.exec(cmd)

    def traffic_control_disable(self):
        self.exec("tc qdisc del dev eth0 root netem")
    
    def is_running(self):
        container = docker_client.containers.get(self.container_name)
        return container.status == "running"

