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

class AssetGenerator {
    constructor(chunkLen) {
        this.chunkLen = chunkLen;
    }

    static randomBool(percentageTrue = 50) {
        return Math.random() < percentageTrue / 100;
    }

    static generateMeasurementArray(arrayLength, axis, expiresSoon = false) {
        let lowerThreshold = 1e-6;
        let upperThreshold = 2e-6;
        let thr = {
            x: 1.8191607053598602e-6,
            y: 1.2442575637320148e-6,
            z: 1.0956301130461567e-6,
        };

        if (expiresSoon == true) {
            upperThreshold = thr[axis];
        }

        let measurementArray = [];
        for (let i = 0; i < arrayLength; i++) {
            measurementArray.push(
                Math.random() * (upperThreshold - lowerThreshold) + lowerThreshold
            );
        }

        return measurementArray;
    }

    getAsset(expiresSoon = undefined) {
        if (expiresSoon == undefined) {
            expiresSoon = AssetGenerator.randomBool();
        }

        let asset = {
            0: {
                x: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "x",
                    expiresSoon
                ),
                y: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "y",
                    expiresSoon
                ),
                z: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "z",
                    expiresSoon
                ),
            },
            1: {
                x: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "x",
                    expiresSoon
                ),
                y: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "y",
                    expiresSoon
                ),
                z: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "z",
                    expiresSoon
                ),
            },
            2: {
                x: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "x",
                    expiresSoon
                ),
                y: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "y",
                    expiresSoon
                ),
                z: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "z",
                    expiresSoon
                ),
            },
            3: {
                x: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "x",
                    expiresSoon
                ),
                y: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "y",
                    expiresSoon
                ),
                z: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "z",
                    expiresSoon
                ),
            },
            4: {
                x: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "x",
                    expiresSoon
                ),
                y: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "y",
                    expiresSoon
                ),
                z: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "z",
                    expiresSoon
                ),
            },
            5: {
                x: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "x",
                    expiresSoon
                ),
                y: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "y",
                    expiresSoon
                ),
                z: AssetGenerator.generateMeasurementArray(
                    this.chunkLen,
                    "z",
                    expiresSoon
                ),
            },
        };
        return asset;
    }
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
        // this.txIndex = 0;
        this.chaincodeID = "";
        this.policyId = "";
        this.chunkLen = 50;

        this.chunkIdList = [];
        this.chunksListBase64 = [];
        this.chunksListPolicyId = [];
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
        const args = this.roundArguments;
        this.chaincodeID = args.chaincodeID ? args.chaincodeID : "basic";
        this.policyId = args.policyId ? args.policyId : "signal_energy_policy_v1";
        this.chunkLen = args.chunkLen ? args.chunkLen : 50;

        // Generate the list of chunks to be added
        let assetGen = new AssetGenerator(this.chunkLen);
        this.chunkIdList = args.numChunks ? generateChunkIds(args.numChunks) : generateChunkIds(1);
        for (let i = 0; i < this.chunkIdList.length; i++) {
            let chunkDataBase64 = Buffer.from(
                JSON.stringify(assetGen.getAsset())
            ).toString("base64");

            this.chunksListBase64.push(chunkDataBase64)
            this.chunksListPolicyId.push(this.policyId)
        }
    }

    /**
     * Assemble TXs for the round.
     * @return {Promise<TxStatus[]>}
     */
    async submitTransaction() {
        // Generate a new dat chunk ID and a sample data
        let args = {
            contractId: this.chaincodeID,
            contractFunction: "AddChunkWithPolicyBatch",
            contractArguments: [
                JSON.stringify(this.chunkIdList),
                JSON.stringify(this.chunksListBase64),
                JSON.stringify(this.chunksListPolicyId)
            ],
            readOnly: false, // TX or query?
        };

        await this.sutAdapter.sendRequests(args);

        for (let i = 0; i < this.chunkIdList.length; i++) {
            let args = {
                contractId: this.chaincodeID,
                contractFunction: "UpdateChunkExpiryDate",
                contractArguments: [this.chunkIdList[i]],
                readOnly: false, // TX or query?
            };

            console.log("Updating expiry date of chunk with ID: " + this.chunkIdList[i]);
            await this.sutAdapter.sendRequests(args);
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