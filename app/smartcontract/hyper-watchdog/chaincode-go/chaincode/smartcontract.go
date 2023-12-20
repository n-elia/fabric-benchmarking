package chaincode

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/golang/protobuf/ptypes"
	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

// SmartContract provides functions for managing an Asset
type SmartContract struct {
	contractapi.Contract
}

// Insert struct field in alphabetic order => to achieve determinism across languages
// golang keeps the order when marshal to json but doesn't order automatically
type Asset struct {
	AppliedPolicyId string        `json:"AppliedPolicyId"`
	ChunkId         string        `json:"ChunkId"`
	DataHash        string        `json:"DataHash"`
	ExpiryDate      time.Time     `json:"ExpiryDate"`
	ExpiryPeriod    time.Duration `json:"ExpiryPeriod"`
}

// === atomic private transactions
// createAsset creates an asset on the world state
func (s *SmartContract) createAsset(ctx contractapi.TransactionContextInterface, a Asset) error {
	exists, err := s.assetExists(ctx, a.ChunkId)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("the asset %s already exists", a.ChunkId)
	}

	assetJSON, err := json.Marshal(a)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(a.ChunkId, assetJSON)
}

// readAsset reads a given asset from the world state
func (s *SmartContract) readAsset(ctx contractapi.TransactionContextInterface, id string) (Asset, error) {
	assetJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return Asset{}, fmt.Errorf("failed to read from world state: %v", err)
	}
	if assetJSON == nil {
		return Asset{}, fmt.Errorf("the asset %s does not exist", id)
	}

	var asset Asset
	err = json.Unmarshal(assetJSON, &asset)
	if err != nil {
		return Asset{}, err
	}

	return asset, nil
}

// updateAsset updates a given asset on the world state
func (s *SmartContract) updateAsset(ctx contractapi.TransactionContextInterface, id string, a Asset) error {
	if a.ChunkId != id {
		return fmt.Errorf("unable to update asset: %s", "given ID is not bound to given asset")
	}

	_, err := s.readAsset(ctx, id)
	if err != nil {
		return fmt.Errorf("unable to update asset: %s", err)
	}

	assetBytes, err := json.Marshal(a)
	if err != nil {
		return err
	}

	return ctx.GetStub().PutState(id, assetBytes)
}

// deleteAsset deletes an given asset from the world state
func (s *SmartContract) deleteAsset(ctx contractapi.TransactionContextInterface, id string) error {
	exists, err := s.assetExists(ctx, id)
	if err != nil {
		return err
	}
	if !exists {
		return fmt.Errorf("the asset %s does not exist", id)
	}

	return ctx.GetStub().DelState(id)
}

// assetExists returns true when asset with given ID exists in world state
func (s *SmartContract) assetExists(ctx contractapi.TransactionContextInterface, id string) (bool, error) {
	assetJSON, err := ctx.GetStub().GetState(id)
	if err != nil {
		return false, fmt.Errorf("failed to read from world state: %v", err)
	}

	return assetJSON != nil, nil
}

// === private transactions
// HistoryQueryResult structure used for returning result of history query
type HistoryQueryResult struct {
	Record    *Asset    `json:"record"`
	TxId      string    `json:"txId"`
	Timestamp time.Time `json:"timestamp"`
	IsDelete  bool      `json:"isDelete"`
}

// getAssetHistory returns the chain of transactions for an asset since issuance.
func (s *SmartContract) getAssetHistory(ctx contractapi.TransactionContextInterface, id string) ([]HistoryQueryResult, error) {
	resultsIterator, err := ctx.GetStub().GetHistoryForKey(id)
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var records []HistoryQueryResult
	for resultsIterator.HasNext() {
		response, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var asset Asset
		if len(response.Value) > 0 {
			err = json.Unmarshal(response.Value, &asset)
			if err != nil {
				return nil, err
			}
		} else {
			asset = Asset{
				ChunkId: id,
			}
		}

		timestamp, err := ptypes.Timestamp(response.Timestamp)
		if err != nil {
			return nil, err
		}

		record := HistoryQueryResult{
			TxId:      response.TxId,
			Timestamp: timestamp,
			Record:    &asset,
			IsDelete:  response.IsDelete,
		}
		records = append(records, record)
	}

	return records, nil
}

// updateAssetExpiryDate updates the ExpiryDate field of an asset
func (s *SmartContract) updateAssetExpiryDate(ctx contractapi.TransactionContextInterface, id string, expiryDate time.Time) error {
	asset, err := s.readAsset(ctx, id)
	if err != nil {
		return err
	}

	asset.ExpiryDate = expiryDate

	return s.updateAsset(ctx, id, asset)
}

// getAssetCreationTime returns the creation timestamp, based on the timestamp of the first transaction
func (s *SmartContract) getAssetCreationTime(ctx contractapi.TransactionContextInterface, id string) (time.Time, error) {
	h, err := s.getAssetHistory(ctx, id)
	if err != nil {
		return time.Time{}, err
	}

	if len(h) == 0 {
		return time.Time{}, fmt.Errorf("asset's history is empty")
	}

	creationTimestamp := h[0].Timestamp // first transaction timestamp
	return creationTimestamp, nil
}

// computeExpiryDate returns a deterministic expiry date, based on asset creation time and expiry period
func (s *SmartContract) computeExpiryDate(ctx contractapi.TransactionContextInterface, id string, expiryPeriod time.Duration) (time.Time, error) {
	// get the asset creation time
	creationTime, err := s.getAssetCreationTime(ctx, id)
	if err != nil {
		return time.Time{}, fmt.Errorf("error getting creation timestamp: %s", err)
	}

	// increase the creation time by expiry period
	expiryDate := creationTime.Add(expiryPeriod)

	return expiryDate, nil
}

// === public transactions
// AddChunk creates an asset for the given chunk
func (s *SmartContract) AddChunk(ctx contractapi.TransactionContextInterface, chunkId, chunkDataBase64 string) error {
	exists, err := s.assetExists(ctx, chunkId)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("the asset %s already exists", chunkId)
	}

	// decode chunkDataBase64, which is a base64 serialized JSON document
	var chunkData ChunkData
	err = base64DecodeJson(&chunkData, chunkDataBase64)
	if err != nil {
		return fmt.Errorf("unable to decode base64 input: %s", err)
	}

	// compute chunk data hash, which is an md5 digest of JSON data chunk
	chunkDataHash, err := chunkData.hash()
	if err != nil {
		return fmt.Errorf("unable to compute data hash: %s", err)
	}

	// assemble the new newAsset
	newAsset := Asset{
		AppliedPolicyId: "",
		ChunkId:         chunkId,
		DataHash:        chunkDataHash,
		ExpiryDate:      time.Time{},
		ExpiryPeriod:    time.Duration(0),
	}

	return s.createAsset(ctx, newAsset)
}

// AddChunkWithPolicy creates an asset for the given chunk and applies the given policy
func (s *SmartContract) AddChunkWithPolicy(ctx contractapi.TransactionContextInterface, chunkId, chunkDataBase64, policyId string) error {
	exists, err := s.assetExists(ctx, chunkId)
	if err != nil {
		return err
	}
	if exists {
		return fmt.Errorf("the asset %s already exists", chunkId)
	}

	// decode chunkDataBase64, which is a base64 serialized JSON document
	var chunkData ChunkData
	err = base64DecodeJson(&chunkData, chunkDataBase64)
	if err != nil {
		return fmt.Errorf("unable to decode base64 input: %s", err)
	}

	// compute chunk data hash, which is an md5 digest of JSON data chunk
	chunkDataHash, err := chunkData.hash()
	if err != nil {
		return fmt.Errorf("unable to compute data hash: %s", err)
	}

	// retrieve and apply the required policy
	chunkExpiryPeriod, err := chunkData.applyPolicyById(policyId)
	if err != nil {
		return fmt.Errorf("unable to apply policy: %s", err)
	}

	// assemble the new asset
	newAsset := Asset{
		AppliedPolicyId: policyId,
		ChunkId:         chunkId,
		DataHash:        chunkDataHash,
		ExpiryDate:      time.Time{},
		ExpiryPeriod:    chunkExpiryPeriod,
	}

	return s.createAsset(ctx, newAsset)
}

// AddChunkWithPolicyBatch batch creates assets for the given chunks and applies the given policy to them
func (s *SmartContract) AddChunkWithPolicyBatch(ctx contractapi.TransactionContextInterface, chunkId, chunkDataBase64, policyId []string) error {
	if len(chunkId) != len(chunkDataBase64) || len(chunkId) != len(policyId) {
		return fmt.Errorf("input arrays have different sizes")
	}

	var newAssets []Asset

	// Check input values and create the new Assets
	for i := range chunkId {
		exists, err := s.assetExists(ctx, chunkId[i])
		if err != nil {
			return err
		}
		if exists {
			return fmt.Errorf("asset with ID %s: the asset already exists", chunkId[i])
		}

		// decode chunkDataBase64, which is a base64 serialized JSON document
		var chunkData ChunkData
		err = base64DecodeJson(&chunkData, chunkDataBase64[i])
		if err != nil {
			return fmt.Errorf("asset with ID %s: unable to decode base64 input: %s", err, chunkId[i])
		}

		// compute chunk data hash, which is a md5 digest of JSON data chunk
		chunkDataHash, err := chunkData.hash()
		if err != nil {
			return fmt.Errorf("asset with ID %s: unable to compute data hash: %s", err, chunkId[i])
		}

		// retrieve and apply the required policy
		chunkExpiryPeriod, err := chunkData.applyPolicyById(policyId[i])
		if err != nil {
			return fmt.Errorf("asset with ID %s: unable to apply policy: %s", err, chunkId[i])
		}

		// assemble the new asset
		newAssets = append(
			newAssets,
			Asset{
				AppliedPolicyId: policyId[i],
				ChunkId:         chunkId[i],
				DataHash:        chunkDataHash,
				ExpiryDate:      time.Time{},
				ExpiryPeriod:    chunkExpiryPeriod,
			},
		)
	}

	for _, newAsset := range newAssets {
		err := s.createAsset(ctx, newAsset)
		if err != nil {
			return fmt.Errorf("failed to put asset to world state. %v", err)
		}
	}
	return nil
}

// ApplyPolicy applies the given policy to the given asset
func (s *SmartContract) ApplyPolicy(ctx contractapi.TransactionContextInterface, chunkId, chunkDataBase64, policyId string) error {
	// read the asset from world state
	asset, err := s.readAsset(ctx, chunkId)
	if err != nil {
		return err
	}

	// decode chunkDataBase64, which is a base64 serialized JSON document
	var chunkData ChunkData
	err = base64DecodeJson(&chunkData, chunkDataBase64)
	if err != nil {
		return fmt.Errorf("unable to decode base64 input: %s", err)
	}

	// compute chunk data hash, which is an md5 digest of JSON data chunk
	givenDataHash, err := chunkData.hash()
	if err != nil {
		return fmt.Errorf("unable to compute data hash: %s", err)
	}

	// assert that the hash of given data is equal to the stored hash
	if asset.DataHash != givenDataHash {
		return fmt.Errorf("unable to apply policy: %s", "given data hash differs from stored one")
	}

	// retrieve and apply the required policy
	chunkExpiryPeriod, err := chunkData.applyPolicyById(policyId)
	if err != nil {
		return fmt.Errorf("unable to apply policy: %s", err)
	}

	// computes the expiry date, starting from creation time
	chunkExpiryDate, err := s.computeExpiryDate(ctx, chunkId, chunkExpiryPeriod)
	if err != nil {
		return fmt.Errorf("unable to apply policy: %s", err)
	}

	// change asset values and update
	asset.AppliedPolicyId = policyId
	asset.ExpiryDate = chunkExpiryDate
	asset.ExpiryPeriod = chunkExpiryPeriod

	return s.updateAsset(ctx, chunkId, asset)
}

// UpdateChunkExpiryDate updates an *existing* asset in the world state with a deterministic expiry time
func (s *SmartContract) UpdateChunkExpiryDate(ctx contractapi.TransactionContextInterface, id string) error {
	// read the asset
	asset, err := s.readAsset(ctx, id)
	if err != nil {
		return fmt.Errorf("error reading the asset: %s", err)
	}

	if (asset.AppliedPolicyId == "") || (asset.ExpiryPeriod == time.Duration(0)) {
		return fmt.Errorf("error updating chunk expiry time: %s", "a policy needs to be applied before computing expiry date")
	}

	// get the asset creation time
	creationTime, err := s.getAssetCreationTime(ctx, id)
	if err != nil {
		return fmt.Errorf("error updating chunk expiry time: %s", err)
	}

	// increase the creation time by expiry period
	expiryDate := creationTime.Add(asset.ExpiryPeriod)

	if expiryDate == asset.ExpiryDate {
		return fmt.Errorf("error updating chunk expiry time: %s", "expiryDate is already present and legit")
	}

	return s.updateAssetExpiryDate(ctx, id, expiryDate)
}

// GetExpiredChunks returns all expired assets found in world state
func (s *SmartContract) GetExpiredChunks(ctx contractapi.TransactionContextInterface, expiryDateRFC3339 string) ([]*Asset, error) {
	givenExpiryTime, err := time.Parse(time.RFC3339, expiryDateRFC3339)
	if err != nil {
		return []*Asset{}, fmt.Errorf("unable to parse expiryDatetime. Please use RFC3339 syntax, e.g. %q", "2014-11-12T11:45:26.371Z")
	}
	if givenExpiryTime.After(time.Now()) {
		return []*Asset{}, fmt.Errorf("queries to future dates are not allowed.")
	}

	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var assets []*Asset
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var asset Asset
		err = json.Unmarshal(queryResponse.Value, &asset)
		if err != nil {
			return nil, err
		}

		var count int = 0
		if (asset.ExpiryDate != time.Time{}) && (asset.ExpiryDate.Before(givenExpiryTime)) { // policy applied, expDate available
			assets = append(assets, &asset)
			count += 1
			if count == 30 {
				break
			}
		}
		// Removed because causes timeout errors when a high number of assets have not been processed yet
		//else if (asset.ExpiryDate == time.Time{}) && (asset.AppliedPolicyId != "") { // policy applied, expDate unavailable
		//// compute the expiry date
		//expiryDate, err := s.computeExpiryDate(ctx, asset.ChunkId, asset.ExpiryPeriod)
		//if err != nil {
		//	continue
		//}
		//// save the expiry date into the asset
		//err = s.updateAssetExpiryDate(ctx, asset.ChunkId, expiryDate)
		//if err != nil {
		//	continue
		//}
		//// append the asset to the returned list
		//assets = append(assets, &asset)
		//}
	}

	return assets, nil
}

// DeleteChunkIfExpired deletes the given asset from the world state, only if it has expired
func (s *SmartContract) DeleteChunkIfExpired(ctx contractapi.TransactionContextInterface, chunkId string) error {
	// read the asset from world state
	asset, err := s.readAsset(ctx, chunkId)
	if err != nil {
		return err
	}

	if asset.AppliedPolicyId == "" {
		return fmt.Errorf("error deleting asset: policy not applied yet")
	}

	if (asset.ExpiryDate == time.Time{}) {
		return fmt.Errorf("error deleting asset: expiry date not computed yet. " +
			"please require 'UpdateChunkExpiryDate' transaction")
	}

	// check expiry date
	now := time.Now()
	if asset.ExpiryDate.After(now) {
		return fmt.Errorf("error deleting asset: expiry date not reached yet")
	}

	return s.deleteAsset(ctx, chunkId)
}

// GetAllAssets returns all assets found in world state
func (s *SmartContract) GetAllAssets(ctx contractapi.TransactionContextInterface) ([]*Asset, error) {
	// range query with empty string for startKey and endKey does an
	// open-ended query of all assets in the chaincode namespace.
	resultsIterator, err := ctx.GetStub().GetStateByRange("", "")
	if err != nil {
		return nil, err
	}
	defer resultsIterator.Close()

	var assets []*Asset
	for resultsIterator.HasNext() {
		queryResponse, err := resultsIterator.Next()
		if err != nil {
			return nil, err
		}

		var asset Asset
		err = json.Unmarshal(queryResponse.Value, &asset)
		if err != nil {
			return nil, err
		}
		assets = append(assets, &asset)
	}

	return assets, nil
}

// Existed returns true if the given chunk appears at least one time within the blockchain
func (s *SmartContract) ChunkExisted(ctx contractapi.TransactionContextInterface, chunkId string) (bool, error) {
	h, err := s.getAssetHistory(ctx, chunkId)
	if err != nil {
		return false, err
	}

	if len(h) == 0 {
		return false, nil
	}

	return true, nil
}

// readAsset reads a given asset from the world state
func (s *SmartContract) ReadChunk(ctx contractapi.TransactionContextInterface, chunkId string) (Asset, error) {
	return s.readAsset(ctx, chunkId)
}
