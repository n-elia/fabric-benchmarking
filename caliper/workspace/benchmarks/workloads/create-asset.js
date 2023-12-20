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
        this.chunkIdList = [];
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
        this.chunkIdList = args.numChunks ? generateChunkIds(args.numChunks) : generateChunkIds(1);

        console.log("chunkIdList: ", this.chunkIdList);
        // this.byteSize = args.byteSize;
    }

    /**
     * Assemble TXs for the round.
     * @return {Promise<TxStatus[]>}
     */
    async submitTransaction() {
        // const uuid = 'client' + this.workerIndex + '_' + this.byteSize + '_' + this.txIndex;
        // this.asset.id = makeid(22);

        // `sendRequests` method of the connector API allows the workload module to submit requests to the SUT.
        // It takes a single parameter: an object or array of objects containing the settings of the requests,
        // with the following structure:
        // - contractId: string. Required. The ID of the contract to call. This is either the unique contractID
        // specified in the network configuration file or the chaincode ID used to deploy the chaincode and must
        // match the id field in the contacts section of channels in the network configuration file.
        // - contractFunction: string. Required. The name of the function to call in the contract.
        // - contractArguments: string[]. Optional. The list of string arguments to pass to the contract.
        // - readOnly: boolean. Optional. Indicates whether the request is a TX or a query. Defaults to false.
        // - transientMap: Map<string, byte[]>. Optional. The transient map to pass to the contract.
        // - invokerIdentity: string. Optional. The name of the user who should invoke the contract. If not provided a user will be selected from the organization defined by invokerMspId or the first organization in the network configuration file if that property is not provided
        // - invokerMspId: string. Optional. The mspid of the user organization who should invoke the contract. Defaults to the first organization in the network configuration file.
        // - targetPeers: string[]. Optional. An array of endorsing peer names as the targets of the transaction proposal. If omitted, the target list will be chosen for you and if discovery is used then the node sdk uses discovery to determine the correct peers.
        // - targetOrganizations: string[]. Optional. An array of endorsing organizations as the targets of the invoke. If both targetPeers and targetOrganizations are specified then targetPeers will take precedence
        // - channel: string. Optional. The name of the channel on which the contract to call resides.
        // - timeout: number. Optional. [Only applies to 1.4 binding when not enabling gateway use] The timeout in seconds to use for this request.
        // - orderer: string. Optional. [Only applies to 1.4 binding when not enabling gateway use] The name of the target orderer for the transaction broadcast. If omitted, then an orderer node of the channel will be automatically selected.

        // Generate a new dat chunk ID and a sample data
        // let chunkId = makeid(22);
        // let chunkDataBase64 = Buffer.from(JSON.stringify(sample_asset)).toString('base64')
        for (let i = 0; i < this.chunkIdList.length; i++) {
            let chunkId = this.chunkIdList[i];
            let chunkDataBase64 = Buffer.from(JSON.stringify(sample_asset)).toString('base64')
            const args = {
                contractId: this.chaincodeID,
                contractFunction: "AddChunk",
                contractArguments: [chunkId, chunkDataBase64],
                readOnly: false, // TX or query?
            };

            console.log('Adding chunk with ID: ' + chunkId);
            await this.sutAdapter.sendRequests(args);
        }

        // const args = {
        //     contractId: this.chaincodeID,
        //     contractFunction: "AddChunk",
        //     contractArguments: [chunkId, chunkDataBase64],
        //     readOnly: false, // TX or query?
        // };

        // console.log('Adding chunk with ID: ' + chunkId);

        // await this.sutAdapter.sendRequests(args);
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