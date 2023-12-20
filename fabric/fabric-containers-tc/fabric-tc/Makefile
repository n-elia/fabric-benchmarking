default: build-all

build-all: build-fabric-ca-tc build-fabric-peer-tc build-fabric-orderer-tc
build-all-and-push: build-and-push-fabric-ca-tc build-and-push-fabric-peer-tc build-and-push-fabric-orderer-tc

# Fabric CA container
build-fabric-ca-tc:
	@echo "Building fabric-ca-tc"
	make -f Makefile.base cnf="./config.fabric-ca.env" build

push-fabric-ca-tc:
	@echo "Pushing fabric-ca-tc"
	make -f Makefile.base cnf="./config.fabric-ca.env" push

build-and-push-fabric-ca-tc: build-fabric-ca-tc push-fabric-ca-tc

# Fabric peer container
build-fabric-peer-tc:
	@echo "Building fabric-peer-tc"
	make -f Makefile.base cnf="./config.fabric-peer.env" build

push-fabric-peer-tc:
	@echo "Pushing fabric-peer-tc"
	make -f Makefile.base cnf="./config.fabric-peer.env" push

build-and-push-fabric-peer-tc: build-fabric-peer-tc push-fabric-peer-tc

# Fabric orderer container
build-fabric-orderer-tc:
	@echo "Building fabric-orderer-tc"
	make -f Makefile.base cnf="./config.fabric-orderer.env" build

push-fabric-orderer-tc:
	@echo "Pushing fabric-orderer-tc"
	make -f Makefile.base cnf="./config.fabric-orderer.env" push

build-and-push-fabric-orderer-tc: build-fabric-orderer-tc push-fabric-orderer-tc
