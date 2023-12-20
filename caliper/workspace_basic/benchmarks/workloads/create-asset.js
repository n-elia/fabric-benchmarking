"use strict"; // enables JS strict mode

const bytes = (s) => {
  return ~-encodeURI(s).split(/%..|./).length;
};

const { WorkloadModuleBase } = require("@hyperledger/caliper-core");
const { log } = require("console");
const { stringify } = require("querystring");

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

/**
 * Load a set of assets from a .csv file and yields them one by one.
 */
function* loadAssets(filePath) {
  const fs = require("fs");

  const fileData = fs.readFileSync(filePath, "utf8");
  const lines = fileData.split("\n");
  const headers = lines[0].replace(/(\r\n|\n|\r)/gm, "").split(",");

  console.log("Got headers: " + headers);

  for (let i = 1; i < lines.length; i++) {
    const currentLine = lines[i].split(",");
    if (currentLine.length !== headers.length) {
      throw new Error("Invalid CSV format");
    }

    const item = {};
    for (let j = 0; j < headers.length; j++) {
      // Parse the value as a number if possible
      if (!isNaN(currentLine[j])) {
        item[headers[j]] = parseInt(currentLine[j]);
      } else {
        item[headers[j]] = currentLine[j];
      }
    }
    yield item;
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

    // Read the asset data from the .csv file
    this.assets = loadAssets(args.assetFile);
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

    for (let i = 0; i < this.roundArguments.assetsPerWorker; i++) {
      // VERSION 1: Generate a random asset ID. Works with multiple workers.
      const assetID = makeid(6);

      // Generate a new asset
      const request = {
          contractId: this.roundArguments.chaincodeID,
          contractFunction: "CreateAsset",
          contractArguments: [assetID,'blue','20','penguin','500'],
          readOnly: false, // TX or query?
      };

      console.log('Adding asset with ID: ' + assetID);

      await this.sutAdapter.sendRequests(request);

      // VERSION 2: Read asset data from a .csv file. Only works with 1 worker.
      // const asset = this.assets.next().value;
      // const request = {
      //   contractId: this.roundArguments.chaincodeID,
      //   contractFunction: "CreateAsset",
      //   contractArguments: [
      //     String(asset.id),
      //     String(asset.color),
      //     String(asset.size),
      //     String(asset.owner),
      //     String(asset.appraisedValue),
      //   ],
      //   readOnly: false, // TX or query?
      // };

      // console.log("Adding asset with ID: " + asset.id);

      // await this.sutAdapter.sendRequests(request);
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
