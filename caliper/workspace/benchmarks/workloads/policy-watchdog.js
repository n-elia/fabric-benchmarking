"use strict"; // enables JS strict mode

const bytes = (s) => {
    return ~-encodeURI(s).split(/%..|./).length;
};

const { WorkloadModuleBase } = require("@hyperledger/caliper-core");

/**
 * Generate a random ID.
 */
function makeid(length = 22) {
    var result = "";
    var characters =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    var charactersLength = characters.length;
    for (var i = 0; i < length; i++) {
        result += characters.charAt(Math.floor(Math.random() * charactersLength));
    }
    return result;
}

function generateChunkIds(numChunks) {
    let chunkIds = [];
    for (let i = 0; i < numChunks; i++) {
        chunkIds.push(makeid());
    }
    return chunkIds;
}

var sample_asset = {
    0: {
        x: [0.00013276679855083346, 0.0012753233219417624],
        y: [-0.0015977911981410356, -0.0003213999292721184],
        z: [0.0005843608670452749, 0.0002824157235010727],
    },
    1: {
        x: [-0.000622898084062254, -0.0008364965981381268],
        y: [0.00046701847943141095, 0.0005736117300911001],
        z: [0.0006042720805841117, 0.000994188547346564],
    },
    2: {
        x: [-0.001652094097505347, 0.002158959741242649],
        y: [-0.0018251231348999234, -0.0023923979032156035],
        z: [0.0006594424153849587, 0.0009469094317833271],
    },
    3: {
        x: [0.0023136999746368255, 0.0018638619155985157],
        y: [-3.796175151765192e-5, 0.001017742758578955],
        z: [0.00013879384121517901, 0.0005850225243821949],
    },
    4: {
        x: [0.0008133573455047727, -0.0015613395814281636],
        y: [0.00048634007914006796, 0.0012047890606415302],
        z: [0.00046315071831304344, 0.00017067558175121178],
    },
    5: {
        x: [-0.0001441341438044036, 0.000406049966185684],
        y: [-0.0014691467559069316, -0.00010501874446107832],
        z: [-0.0003473290806594864, -0.0007617954302484575],
    },
};

function* makeRangeIterator(inputArray) {
    let iterationCount = 0;
    for (let i = 0; i < inputArray.length; i += 1) {
        iterationCount++;
        yield inputArray[i];
    }
    return iterationCount;
}

/**
 * The interface contains the following three asynchronous functions.
 * Workload module for the benchmark round.
 */
class CreateAssetWorkload extends WorkloadModuleBase {
    /**
     * Initializes the workload module instance.
     */
    constructor() {
        super();
        this.chaincodeID = "";
        this.expiredChunksList = [];
        // this.expChunkIdsIterator;
    }

    /**
     * The `initializeWorkloadModule` function is called by the worker processes before each round,
     * providing contextual arguments to the module, thus initializes the workload module with the
     * given parameters:
     * @param {number} workerIndex The 0-based index of the worker instantiating the workload module.
     * @param {number} totalWorkers The total number of workers participating in the round.
     * @param {number} roundIndex The 0-based index of the currently executing round.
     * @param {Object} roundArguments The user-provided arguments for the round from the benchmark configuration file.
     * @param {BlockchainInterface} sutAdapter The adapter of the underlying SUT.
     * @param {Object} sutContext The custom context object provided by the SUT adapter.
     * @async
     * Note: This function is a good place to validate your workload module arguments provided by the benchmark
     * configuration file. It’s also a good practice to perform here any preprocessing needed to ensure the
     * fast assembling of TX contents later in the submitTransaction function.
     */
    async initializeWorkloadModule(
        workerIndex,
        totalWorkers,
        roundIndex,
        roundArguments,
        sutAdapter,
        sutContext
    ) {
        await super.initializeWorkloadModule(
            workerIndex,
            totalWorkers,
            roundIndex,
            roundArguments,
            sutAdapter,
            sutContext
        );

        // The user-provided arguments for the round (from .yaml config file)
        const workloadArgs = this.roundArguments;
        this.chaincodeID = workloadArgs.chaincodeID ?
            workloadArgs.chaincodeID :
            "basic";
    }

    /**
     * Assemble TXs for the round.
     * @return {Promise<TxStatus[]>}
     */
    async submitTransaction() {
        // // Generate a new dat chunk ID and a sample data
        // let chunkId = this.expChunkIdsIterator.next().value;
        // if (chunkId === undefined) {
        //     console.log("No more expired chunks to delete");
        //     return;
        // }
        // let args = {
        //     contractId: this.chaincodeID,
        //     contractFunction: "DeleteChunkIfExpired",
        //     contractArguments: [chunkId],
        //     readOnly: false, // TX or query?
        // };
        // console.log("Deleting chunk: ", chunkId);

        // await this.sutAdapter.sendRequests(args);

        while (true) {
            // Query the expired assets to be deleted
            let timestampRFC3339 = new Date().toISOString();
            let args = {
                contractId: this.chaincodeID,
                contractFunction: "GetExpiredChunks",
                contractArguments: [timestampRFC3339],
                readOnly: false, // TX or query?
            };

            console.log("Getting expired chunks...");
            let res = await this.sutAdapter.sendRequests(args);
            let resString = new TextDecoder().decode(res.status.result);
            if (resString.length == 0) {
                console.log("No expired chunks found");
                break;
            } else {
                let resJSON = JSON.parse(resString);
                for (let j = 0; j < resJSON.length; j++) {
                    // console.debug("Expired chunk: ", resJSON[j]);
                    this.expiredChunksList.push(resJSON[j].ChunkId);
                }
                console.debug("Expired chunks IDs: ", this.expiredChunksList);

                // this.expChunkIdsIterator = makeRangeIterator(this.expiredChunksList);
            }

            if (this.expiredChunksList.length == 0) {
                console.log("No expired chunks to delete");
                break;
            } else {
                for (let i = 0; i < this.expiredChunksList.length; i++) {
                    let chunkId = this.expiredChunksList[i]
                    console.log("Deleting chunk: ", chunkId);

                    let args = {
                        contractId: this.chaincodeID,
                        contractFunction: "DeleteChunkIfExpired",
                        contractArguments: [chunkId],
                        readOnly: false, // TX or query?
                    };

                    await this.sutAdapter.sendRequests(args);
                }
            }
        }


    }
}

/**
 * Note: a workload module implementation must export a single factory function,
 * named createWorkloadModule. It will create a new instance of the workload module.
 * @return {WorkloadModuleInterface}
 * Therefore, it must return an instance that implements the WorkloadModuleInterface class.
 */
function createWorkloadModule() {
    return new CreateAssetWorkload();
}

module.exports.createWorkloadModule = createWorkloadModule;